"""Reine Release-Helfer: Namen, Hashes, Docs, ZIP, Pruefungen.

Keine CNC-Logik. Kein Nuitka-Compile in diesem Modul.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from app_info import (  # noqa: E402
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_EMAIL,
    APP_NAME,
    APP_VERSION,
    APP_WEBSITE,
    BSF_REAL_TOOL_VALIDATED,
    EXE_FILENAME,
    WINDOWS_FILE_VERSION,
    WINDOWS_PRODUCT_VERSION,
    derive_windows_version,
)


class ReleaseAborted(Exception):
    """Kontrollierter Abbruch; kein erfolgreiches Release melden."""


IMAGE_FILE_MACHINE_I386 = 0x14C
IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_ARM64 = 0xAA64

APP_SOURCE_RELATIVE = (
    "app_info.py",
    "app_paths.py",
    "runtime_smoke.py",
    "nc_programmer.py",
    "bsf_generator_verbessert_v3.py",
    "bsf_blade.py",
    "bgf_depth.py",
    "bgf_depth_approvals.py",
    "bgf_depth_reference.py",
    "bgf_surface.py",
    "bgf_variable_depth.py",
    "assets/app_icon.ico",
    "assets/app_icon.png",
)
APP_SOURCE_TREES = ("coordinates", "preview", "help_views", "ui")

DIST_STRIP_NAMES = frozenset(
    {
        "nuitka-compilation-report.xml",
        ".git",
        "__pycache__",
    }
)

FORBIDDEN_SOURCE_SUFFIXES = (".py", ".pyc", ".pyw", ".pyo")
FORBIDDEN_DIR_NAMES = frozenset({"tests", ".git", "build_tools", "__pycache__"})
USER_PROJECT_SUFFIXES = (".bgf.json", ".bsf.json", ".csv", ".h")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def posix_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def arch_from_pointer_and_machine(pointer_bits: int, machine: str) -> str:
    name = (machine or "").lower().strip()
    if pointer_bits == 64 and name in {"amd64", "x86_64", "x64"}:
        return "x64"
    if pointer_bits == 32 and name in {"x86", "i386", "i686"}:
        return "x86"
    if pointer_bits == 32 and name == "amd64":
        return "x86"
    if pointer_bits == 64 and name in {"arm64", "aarch64"}:
        return "arm64"
    raise ReleaseAborted(f"Nicht unterstuetzte Architektur: machine={machine!r} bits={pointer_bits}")


def windows_platform_tag(arch: str) -> str:
    return f"Windows_{arch}"


def python_architecture() -> str:
    return arch_from_pointer_and_machine(struct.calcsize("P") * 8, platform.machine())


def pe_machine(exe: Path) -> int:
    with exe.open("rb") as handle:
        header = handle.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise ReleaseAborted(f"Keine PE-Datei: {exe}")
        e_lfanew = struct.unpack_from("<I", header, 60)[0]
        handle.seek(e_lfanew)
        sig = handle.read(6)
        if sig[:4] != b"PE\0\0":
            raise ReleaseAborted(f"Kein PE-Signatur: {exe}")
        return struct.unpack_from("<H", sig, 4)[0]


def pe_architecture(exe: Path) -> str:
    machine = pe_machine(exe)
    if machine == IMAGE_FILE_MACHINE_AMD64:
        return "x64"
    if machine == IMAGE_FILE_MACHINE_I386:
        return "x86"
    if machine == IMAGE_FILE_MACHINE_ARM64:
        return "arm64"
    raise ReleaseAborted(f"Unbekannte PE-Maschine 0x{machine:04x} in {exe}")


def confirm_release_architecture(exe: Path) -> str:
    py_arch = python_architecture()
    exe_arch = pe_architecture(exe)
    if py_arch != exe_arch:
        raise ReleaseAborted(f"Architektur-Konflikt: Python={py_arch} EXE={exe_arch}")
    return exe_arch


def release_folder_name(app_version: str, platform_tag: str) -> str:
    derive_windows_version(app_version)
    if not platform_tag.startswith("Windows_"):
        raise ReleaseAborted(f"Unerwarteter Plattform-Tag: {platform_tag}")
    stem = Path(EXE_FILENAME).stem
    return f"{stem}_{app_version}_{platform_tag}"


def iter_app_source_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for rel in APP_SOURCE_RELATIVE:
        path = root / rel
        if path.is_file():
            files.append(path)
    for tree in APP_SOURCE_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        files.extend(sorted(p for p in base.rglob("*.py") if p.is_file()))
    unique = []
    seen = set()
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return sorted(unique, key=lambda p: str(p).lower())


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_app_source_files(root):
        rel = posix_rel(path, root)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def detect_nuitka_version() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "nuitka", "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ReleaseAborted("Nuitka-Version nicht lesbar.")
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        raise ReleaseAborted("Nuitka-Version leer.")
    return line[0].strip()


def git_info(root: Path) -> Dict[str, Optional[object]]:
    git_dir = root / ".git"
    if not git_dir.exists():
        return {
            "git_available": False,
            "git_commit": None,
            "git_branch": None,
            "git_dirty": None,
        }

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    commit_p = git("rev-parse", "HEAD")
    branch_p = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty_p = git("status", "--porcelain")
    if commit_p.returncode != 0:
        return {
            "git_available": False,
            "git_commit": None,
            "git_branch": None,
            "git_dirty": None,
        }
    dirty = bool((dirty_p.stdout or "").strip())
    return {
        "git_available": True,
        "git_commit": (commit_p.stdout or "").strip() or None,
        "git_branch": (branch_p.stdout or "").strip() or None,
        "git_dirty": dirty,
    }


def build_manifest_payload(
    root: Path,
    *,
    architecture: str,
    console: bool = False,
) -> Dict[str, object]:
    git = git_info(root)
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "windows_file_version": WINDOWS_FILE_VERSION,
        "windows_product_version": WINDOWS_PRODUCT_VERSION,
        "python_version": platform.python_version(),
        "nuitka_version": detect_nuitka_version(),
        "architecture": architecture,
        "build_mode": "standalone",
        "console": console,
        "exe_filename": EXE_FILENAME,
        "bsf_real_tool_validated": BSF_REAL_TOOL_VALIDATED,
        "source_fingerprint": source_fingerprint(root),
        "build_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git["git_commit"],
        "git_branch": git["git_branch"],
        "git_dirty": git["git_dirty"],
        "git_available": git["git_available"],
    }


def write_build_manifest(root: Path, exe: Path, *, console: bool = False) -> Path:
    architecture = confirm_release_architecture(exe)
    payload = build_manifest_payload(root, architecture=architecture, console=console)
    out = root / "build" / "build_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def load_build_manifest(root: Path) -> Dict[str, object]:
    path = root / "build" / "build_manifest.json"
    if not path.is_file():
        raise ReleaseAborted(f"Build-Manifest fehlt: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def bsf_validation_label() -> str:
    return "YES" if BSF_REAL_TOOL_VALIDATED else "PENDING"


def render_readme(app_version: str = APP_VERSION) -> str:
    pending = ""
    if not BSF_REAL_TOOL_VALIDATED:
        pending = (
            f"Hinweis Version {app_version}:\n"
            "Die abschließende Realwerkzeug-Validierung für HEULE BSF\n"
            "ist zum Erstellzeitpunkt dieses Pakets noch ausstehend.\n"
            "\n"
        )
    return (
        f"NC-Code Generator – Version {app_version}\n"
        "\n"
        "Start:\n"
        f"{EXE_FILENAME}\n"
        "\n"
        "Unterstützte Bearbeitungen:\n"
        "- CERATIZIT BGF\n"
        "- HEULE BSF\n"
        "\n"
        "Positionierungsarten:\n"
        "- Teilkreis\n"
        "- Einzelposition\n"
        "- Koordinatenliste\n"
        "\n"
        "Projektdateien:\n"
        "- .bgf.json\n"
        "- .bsf.json\n"
        "\n"
        "Datenaustausch:\n"
        "- CSV\n"
        "\n"
        "NC-Ausgabe:\n"
        "- Heidenhain .H\n"
        "\n"
        "Portable Installation:\n"
        "Der gesamte Programmordner muss zusammenbleiben.\n"
        f"Nicht nur {EXE_FILENAME} einzeln aus dem Ordner kopieren.\n"
        "\n"
        "WICHTIG:\n"
        "Erzeugte NC-Programme vor Einsatz an der Maschine vollständig prüfen.\n"
        "Werkzeugdaten, Nullpunkt, Werkzeugradius, Werkzeuglänge,\n"
        "M-Funktionen, Drehrichtung, Vorschub und Kollisionsfreiheit prüfen.\n"
        "\n"
        "Die Schwertdicke und Vermessreferenz müssen der tatsächlichen\n"
        "Werkzeugvermessung entsprechen.\n"
        "\n"
        f"{pending}"
        "Die Software ersetzt keine Prüfung des erzeugten NC-Programms\n"
        "an Maschine bzw. Simulation.\n"
    )


def render_release_info(manifest: Dict[str, object]) -> str:
    python_v = str(manifest.get("python_version") or platform.python_version())
    nuitka_v = str(manifest.get("nuitka_version") or "")
    arch = str(manifest.get("architecture") or "")
    return (
        f"{APP_NAME}\n"
        f"Version {APP_VERSION}\n"
        "\n"
        "RELEASE PACKAGE TYPE:\n"
        "TECHNICAL RELEASE PACKAGE\n"
        "\n"
        "Entwicklung:\n"
        f"{APP_AUTHOR}\n"
        "\n"
        "Web:\n"
        f"{APP_WEBSITE}\n"
        "\n"
        "E-Mail:\n"
        f"{APP_EMAIL}\n"
        "\n"
        "Plattform:\n"
        f"Windows {arch}\n"
        "\n"
        "Build:\n"
        "Nuitka Standalone\n"
        "\n"
        "Python:\n"
        f"{python_v}\n"
        "\n"
        "Nuitka:\n"
        f"{nuitka_v}\n"
        "\n"
        "HEULE BSF REAL TOOL VALIDATION:\n"
        f"{bsf_validation_label()}\n"
        "\n"
        "Die Software ersetzt keine Prüfung des erzeugten NC-Programms\n"
        "an Maschine bzw. Simulation.\n"
    )


def iter_files(root: Path) -> List[Path]:
    files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: posix_rel(p, root).lower())


def sha256sums_text(root: Path) -> str:
    lines = []
    for path in iter_files(root):
        rel = posix_rel(path, root)
        if rel == "SHA256SUMS.txt":
            continue
        lines.append(f"{sha256_file(path)}  {rel}")
    return "\n".join(lines) + ("\n" if lines else "")


def write_sha256sums(root: Path) -> Path:
    text = sha256sums_text(root)
    out = root / "SHA256SUMS.txt"
    out.write_text(text, encoding="utf-8")
    return out


def verify_sha256sums(root: Path) -> None:
    sums = root / "SHA256SUMS.txt"
    if not sums.is_file():
        raise ReleaseAborted("SHA256SUMS.txt fehlt.")
    listed = {}
    for raw in sums.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        digest, name = line.split("  ", 1)
        listed[name] = digest.lower()
    expected = {}
    for path in iter_files(root):
        rel = posix_rel(path, root)
        if rel == "SHA256SUMS.txt":
            continue
        expected[rel] = sha256_file(path)
    if listed != expected:
        raise ReleaseAborted("SHA256SUMS.txt stimmt nicht mit den Dateien ueberein.")


def scan_forbidden(root: Path) -> Dict[str, List[str]]:
    source: List[str] = []
    tests_or_tools: List[str] = []
    user_files: List[str] = []
    for path in iter_files(root):
        rel = posix_rel(path, root)
        parts = set(Path(rel).parts)
        lower = rel.lower()
        if lower.endswith(FORBIDDEN_SOURCE_SUFFIXES):
            source.append(rel)
        if parts & FORBIDDEN_DIR_NAMES or lower.endswith("nuitka-compilation-report.xml"):
            tests_or_tools.append(rel)
        if lower.endswith(USER_PROJECT_SUFFIXES):
            user_files.append(rel)
    return {
        "source": source,
        "dev": tests_or_tools,
        "user": user_files,
    }


def assert_clean_payload(root: Path) -> None:
    found = scan_forbidden(root)
    if found["source"]:
        raise ReleaseAborted(
            "Unerlaubte Quelldateien im Release: " + ", ".join(found["source"][:8])
        )
    if found["dev"]:
        raise ReleaseAborted(
            "Unerlaubte Entwicklungsdateien im Release: " + ", ".join(found["dev"][:8])
        )
    if found["user"]:
        raise ReleaseAborted(
            "Unerlaubte Projektdateien im Release: " + ", ".join(found["user"][:8])
        )


def _on_rm_error(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    import shutil

    if path.is_dir():
        shutil.rmtree(path, onerror=_on_rm_error)
    elif path.is_file():
        path.unlink()


def copy_dist(dist: Path, dest: Path) -> None:
    import shutil

    if not dist.is_dir():
        raise ReleaseAborted(f"Dist fehlt: {dist}")
    if dest.exists():
        remove_tree(dest)
    shutil.copytree(dist, dest, ignore=shutil.ignore_patterns(*DIST_STRIP_NAMES))


def write_release_docs(dest: Path, changelog_src: Path, manifest: Dict[str, object]) -> None:
    if not changelog_src.is_file():
        raise ReleaseAborted(f"CHANGELOG.md fehlt: {changelog_src}")
    (dest / "README.txt").write_text(render_readme(), encoding="utf-8")
    (dest / "CHANGELOG.txt").write_text(changelog_src.read_text(encoding="utf-8"), encoding="utf-8")
    (dest / "RELEASE_INFO.txt").write_text(render_release_info(manifest), encoding="utf-8")


def create_zip(folder: Path, zip_path: Path, top_name: str) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files(folder):
            rel = posix_rel(path, folder)
            archive.write(path, f"{top_name}/{rel}")


def zip_top_level_entries(zip_path: Path) -> List[str]:
    names: List[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            top = name.split("/", 1)[0]
            if top and top not in names:
                names.append(top)
    return names


def assert_zip_top_level(zip_path: Path, expected: str) -> None:
    tops = zip_top_level_entries(zip_path)
    if tops != [expected]:
        raise ReleaseAborted(f"ZIP Top-Level unerwartet: {tops!r} (erwartet {[expected]!r})")


def write_zip_sha256(zip_path: Path) -> Tuple[Path, str]:
    digest = sha256_file(zip_path)
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return sidecar, digest


def verify_zip_sha256(zip_path: Path, sidecar: Path) -> str:
    text = sidecar.read_text(encoding="utf-8")
    listed = text.strip().split()
    if not listed:
        raise ReleaseAborted("ZIP-SHA256-Datei leer.")
    expected = listed[0].lower()
    actual = sha256_file(zip_path)
    if actual != expected:
        raise ReleaseAborted("ZIP-SHA256 stimmt nach erneutem Lesen nicht.")
    if zip_path.name not in text:
        raise ReleaseAborted("ZIP-SHA256 enthaelt nicht den Dateinamen.")
    return actual


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def read_exe_version_info(exe: Path) -> Dict[str, str]:
    if sys.platform != "win32":
        raise ReleaseAborted("EXE-Metadaten nur unter Windows lesbar.")
    import ctypes
    from ctypes import wintypes

    version = ctypes.WinDLL("version")
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [
        wintypes.LPCVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    version.VerQueryValueW.restype = wintypes.BOOL

    dummy = wintypes.DWORD()
    size = version.GetFileVersionInfoSizeW(str(exe), ctypes.byref(dummy))
    if not size:
        raise ReleaseAborted(f"Keine Versionsressource in {exe}")
    buf = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(exe), 0, size, buf):
        raise ReleaseAborted(f"GetFileVersionInfoW fehlgeschlagen: {exe}")

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
            ("dwFileFlagsMask", wintypes.DWORD),
            ("dwFileFlags", wintypes.DWORD),
            ("dwFileOS", wintypes.DWORD),
            ("dwFileType", wintypes.DWORD),
            ("dwFileSubtype", wintypes.DWORD),
            ("dwFileDateMS", wintypes.DWORD),
            ("dwFileDateLS", wintypes.DWORD),
        ]

    lptr = ctypes.c_void_p()
    ulen = wintypes.UINT()
    if not version.VerQueryValueW(buf, "\\", ctypes.byref(lptr), ctypes.byref(ulen)):
        raise ReleaseAborted("VS_FIXEDFILEINFO nicht lesbar.")
    info = ctypes.cast(lptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents

    def dotted(ms: int, ls: int) -> str:
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"

    def query_string(lang: str, key: str) -> str:
        sub = f"\\StringFileInfo\\{lang}\\{key}"
        sptr = ctypes.c_void_p()
        slen = wintypes.UINT()
        if version.VerQueryValueW(buf, sub, ctypes.byref(sptr), ctypes.byref(slen)) and sptr.value:
            return ctypes.wstring_at(sptr.value)
        return ""

    lang = "040904b0"
    tptr = ctypes.c_void_p()
    tlen = wintypes.UINT()
    if version.VerQueryValueW(
        buf, "\\VarFileInfo\\Translation", ctypes.byref(tptr), ctypes.byref(tlen)
    ):
        if tptr.value and tlen.value >= 4:
            words = ctypes.cast(tptr, ctypes.POINTER(wintypes.WORD))
            lang = f"{words[0]:04x}{words[1]:04x}"

    return {
        "ProductName": query_string(lang, "ProductName"),
        "FileDescription": query_string(lang, "FileDescription"),
        "LegalCopyright": query_string(lang, "LegalCopyright"),
        "CompanyName": query_string(lang, "CompanyName"),
        "FileVersion": query_string(lang, "FileVersion")
        or dotted(info.dwFileVersionMS, info.dwFileVersionLS),
        "ProductVersion": query_string(lang, "ProductVersion")
        or dotted(info.dwProductVersionMS, info.dwProductVersionLS),
        "FileVersionNumeric": dotted(info.dwFileVersionMS, info.dwFileVersionLS),
        "ProductVersionNumeric": dotted(info.dwProductVersionMS, info.dwProductVersionLS),
    }


def assert_exe_matches_app_info(exe: Path) -> Dict[str, str]:
    meta = read_exe_version_info(exe)
    numeric = meta["FileVersionNumeric"]
    product_numeric = meta["ProductVersionNumeric"]
    if numeric != WINDOWS_FILE_VERSION or product_numeric != WINDOWS_PRODUCT_VERSION:
        raise ReleaseAborted(
            f"EXE-Version {numeric}/{product_numeric} != {WINDOWS_FILE_VERSION}/{WINDOWS_PRODUCT_VERSION}"
        )
    product_s = meta.get("ProductVersion") or ""
    if product_s not in {APP_VERSION, WINDOWS_PRODUCT_VERSION} and APP_VERSION not in product_s:
        if product_numeric != WINDOWS_PRODUCT_VERSION:
            raise ReleaseAborted("ProductVersion der EXE weicht ab.")
    if meta.get("ProductName") and meta["ProductName"] != APP_NAME:
        raise ReleaseAborted(f"ProductName {meta['ProductName']!r} != {APP_NAME!r}")
    desc = meta.get("FileDescription") or ""
    if desc and desc != APP_DESCRIPTION:
        raise ReleaseAborted(f"FileDescription weicht ab: {desc!r}")
    return meta


def assert_docs_match_app_info(folder: Path) -> None:
    readme = (folder / "README.txt").read_text(encoding="utf-8")
    info = (folder / "RELEASE_INFO.txt").read_text(encoding="utf-8")
    for blob in (readme, info):
        if APP_NAME not in blob:
            raise ReleaseAborted("APP_NAME fehlt in Release-Dokumenten.")
        if APP_VERSION not in blob:
            raise ReleaseAborted("APP_VERSION fehlt in Release-Dokumenten.")
    if APP_AUTHOR not in info or APP_WEBSITE not in info or APP_EMAIL not in info:
        raise ReleaseAborted("Autor/Web/E-Mail fehlen in RELEASE_INFO.txt.")
    if "HEULE BSF REAL TOOL VALIDATION:" not in info:
        raise ReleaseAborted("BSF-Validierungsstatus fehlt in RELEASE_INFO.txt.")
    if not BSF_REAL_TOOL_VALIDATED:
        if "PENDING" not in info:
            raise ReleaseAborted("PENDING-Status fehlt in RELEASE_INFO.txt.")
        if "noch ausstehend" not in readme:
            raise ReleaseAborted("BSF-Hinweis fehlt in README.txt.")
    forbidden_claim = "HEULE real tool validation completed"
    joined = (readme + "\n" + info).lower()
    if forbidden_claim.lower() in joined:
        raise ReleaseAborted("Unzulaessige Validierungsaussage in Release-Dokumenten.")


def require_dist(dist: Path, exe: Path) -> None:
    if not dist.is_dir():
        raise ReleaseAborted(f"Nuitka-Dist fehlt: {dist}")
    if not exe.is_file() or exe.stat().st_size <= 0:
        raise ReleaseAborted(f"EXE fehlt oder leer: {exe}")


def assert_release_paths(folder: Path, zip_path: Path, root: Path) -> None:
    release_root = (root / "release").resolve()
    folder_r = folder.resolve()
    zip_r = zip_path.resolve()
    if folder_r.parent != release_root:
        raise ReleaseAborted(f"Releaseordner liegt nicht unter release/: {folder_r}")
    if zip_r.parent != release_root:
        raise ReleaseAborted(f"ZIP liegt nicht unter release/: {zip_r}")
    if folder_r.name != zip_path.stem:
        raise ReleaseAborted("ZIP-Name und Releaseordner stimmen nicht ueberein.")
