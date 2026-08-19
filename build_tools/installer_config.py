"""Inno-Setup-Konfiguration und Helfer fuer den Windows-Installer.

Keine CNC-Fachlogik. Kein Nuitka-Build.
Produktmetadaten kommen aus app_info.py.
AppId ist die stabile Upgrade-Identitaet und darf nie geaendert werden.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
import sys

if str(_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
if str(_ROOT_FOR_IMPORT / "build_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "build_tools"))

from app_info import (  # noqa: E402
    APP_AUTHOR,
    APP_COPYRIGHT,
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    APP_WEBSITE_URL,
    EXE_FILENAME,
    WINDOWS_COMPANY_NAME,
    WINDOWS_FILE_VERSION,
    derive_windows_version,
)
from app_paths import APP_ICON_ICO_REL  # noqa: E402
from release_packaging import (  # noqa: E402
    ReleaseAborted,
    assert_clean_payload,
    assert_exe_matches_app_info,
    load_build_manifest,
    pe_architecture,
    project_root,
    scan_forbidden,
    sha256_file,
    source_fingerprint,
)

# Stable Inno Setup AppId. NEVER change between versions.
# Format for [Setup] AppId={#MyAppId} is {{GUID}} (doubled braces).
INNO_APP_ID_GUID = "AC33C948-D619-47A0-8809-D99468EF9297"
INNO_APP_ID = "{{" + INNO_APP_ID_GUID + "}}"
APP_ID_STABLE = True

INNO_SETUP_NOT_FOUND = "INNO_SETUP_NOT_FOUND"
ISS_RELATIVE = Path("installer") / "NC-Code-Generator.iss"
INSTALLER_OUTPUT_DIR_REL = Path("installer") / "output"
DEFINES_GENERATED_REL = Path("installer") / "defines.generated.iss"
DEFAULT_INSTALL_DIR_INNO = r"{autopf}\NC-Code Generator"
CODE_SIGNING = "NOT_CONFIGURED"
DOWNGRADE_BLOCK_MESSAGE = (
    "Eine neuere Version des NC-Code Generators ist bereits installiert."
)
VERSION_GUARD_REL = Path("installer") / "version_guard.iss"
# Isolated installer tests only. Never used by the product ISS.
TEST_APP_ID_GUID = "8F3C2A91-6B47-4E0D-9C55-2D7A1E4B8C10"
TEST_APP_ID = "{{" + TEST_APP_ID_GUID + "}}"

_GUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)


class InstallerAborted(Exception):
    """Kontrollierter Abbruch der Installer-Pipeline."""


def iss_script_path(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / ISS_RELATIVE


def setup_icon_path(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / APP_ICON_ICO_REL


def installer_output_dir(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / INSTALLER_OUTPUT_DIR_REL


def installer_basename(app_version: str = APP_VERSION) -> str:
    return f"NC-Code-Generator-Setup-{app_version}"


def installer_filename(app_version: str = APP_VERSION) -> str:
    return f"{installer_basename(app_version)}.exe"


def installer_sha256_filename(app_version: str = APP_VERSION) -> str:
    return f"{installer_filename(app_version)}.sha256"


def write_installer_sha256(installer_path: Path) -> Tuple[Path, str]:
    digest = sha256_file(installer_path)
    sidecar = installer_path.with_suffix(installer_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {installer_path.name}\n", encoding="utf-8")
    return sidecar, digest


def verify_installer_sha256(installer_path: Path, sidecar: Path) -> str:
    text = sidecar.read_text(encoding="utf-8")
    listed = text.strip().split()
    if not listed:
        raise InstallerAborted("Installer-SHA256-Datei leer.")
    expected = listed[0].lower()
    actual = sha256_file(installer_path)
    if actual != expected:
        raise InstallerAborted("Installer-SHA256 stimmt nicht.")
    if installer_path.name not in text:
        raise InstallerAborted("Installer-SHA256 enthaelt nicht den Dateinamen.")
    return actual


def _env_iscc_candidate() -> Optional[Path]:
    raw = os.environ.get("INNO_SETUP_COMPILER", "").strip().strip('"')
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return path.resolve()
    if path.is_dir():
        exe = path / "ISCC.exe"
        if exe.is_file():
            return exe.resolve()
    return None


def _typical_iscc_candidates() -> List[Path]:
    candidates: List[Path] = []
    bases: List[Path] = []
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        value = os.environ.get(key, "").strip()
        if value:
            bases.append(Path(value))
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        bases.append(Path(local) / "Programs")
    for base in bases:
        for folder in ("Inno Setup 6", "Inno Setup 5"):
            candidates.append(base / folder / "ISCC.exe")
    return candidates


def find_iscc() -> Optional[Path]:
    """Finde ISCC.exe: Env, typische Pfade, PATH. Keine Auto-Installation."""
    env_candidate = _env_iscc_candidate()
    if os.environ.get("INNO_SETUP_COMPILER", "").strip():
        return env_candidate

    for path in _typical_iscc_candidates():
        if path.is_file():
            return path.resolve()

    which = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if which:
        found = Path(which)
        if found.is_file():
            return found.resolve()
    return None


def require_iscc() -> Path:
    found = find_iscc()
    if found is None:
        raise InstallerAborted(INNO_SETUP_NOT_FOUND)
    return found


def iscc_version_label(iscc: Path) -> str:
    """Beste verfuegbare Versionskennzeichnung (Banner oder Pfad)."""
    try:
        completed = subprocess.run(
            [str(iscc)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        blob = (completed.stdout or "") + "\n" + (completed.stderr or "")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("compiler engine version:"):
                return stripped.split(":", 1)[1].strip()
            if "Inno Setup" in stripped and any(ch.isdigit() for ch in stripped):
                if "Copyright" not in stripped:
                    return stripped
    except (OSError, subprocess.TimeoutExpired):
        pass
    parent = iscc.parent.name
    if "Inno Setup" in parent:
        return parent
    return str(iscc)


def default_payload_dir(root: Optional[Path] = None) -> Path:
    base = root or project_root()
    release_name = f"NC-Code-Generator_{APP_VERSION}_Windows_x64"
    return base / "release" / release_name


def resolve_payload_dir(root: Path, explicit: Optional[Path] = None) -> Path:
    if explicit is not None:
        payload = explicit
    else:
        payload = default_payload_dir(root)
        if not payload.is_dir():
            from nuitka_standalone import dist_exe_path

            dist_exe = dist_exe_path(root)
            if dist_exe.is_file():
                payload = dist_exe.parent
    if not payload.is_dir():
        raise InstallerAborted(f"Installer-Payload fehlt: {payload}")
    return payload.resolve()


def _assert_no_pdf(payload: Path) -> None:
    pdfs = [p for p in payload.rglob("*.pdf") if p.is_file()]
    if pdfs:
        raise InstallerAborted(
            "PDF im Installer-Payload nicht erlaubt: "
            + ", ".join(p.name for p in pdfs[:5])
        )


def _assert_runtime_present(payload: Path) -> None:
    exe = payload / EXE_FILENAME
    if not exe.is_file() or exe.stat().st_size <= 0:
        raise InstallerAborted(f"EXE fehlt im Payload: {exe}")
    dlls = list(payload.glob("*.dll"))
    if not dlls:
        raise InstallerAborted("Keine Runtime-DLLs im Payload (Nuitka-Standalone erwartet).")
    icon = payload / APP_ICON_ICO_REL
    if not icon.is_file():
        raise InstallerAborted(f"Icon fehlt im Payload: {icon}")


def validate_installer_payload(root: Path, payload: Path) -> Dict[str, object]:
    """Prueft geprueften Standalone-/Release-Stand vor dem Installer-Build."""
    _assert_runtime_present(payload)
    _assert_no_pdf(payload)
    assert_clean_payload(payload)

    exe = payload / EXE_FILENAME
    arch = pe_architecture(exe)
    if arch != "x64":
        raise InstallerAborted(f"Installer erwartet x64-Payload, gefunden: {arch}")
    exe_meta = assert_exe_matches_app_info(exe)

    try:
        manifest = load_build_manifest(root)
    except ReleaseAborted as exc:
        raise InstallerAborted(str(exc)) from exc

    if manifest.get("app_version") != APP_VERSION:
        raise InstallerAborted(
            f"Version-Drift: Manifest {manifest.get('app_version')!r} != APP_VERSION {APP_VERSION!r}"
        )
    if manifest.get("windows_file_version") != WINDOWS_FILE_VERSION:
        raise InstallerAborted(
            "Version-Drift: Manifest windows_file_version weicht von app_info ab."
        )
    expected_fp = source_fingerprint(root)
    if manifest.get("source_fingerprint") != expected_fp:
        raise InstallerAborted(
            "Source-Fingerprint im Manifest stimmt nicht mit aktuellem Source ueberein."
        )

    forbidden = scan_forbidden(payload)
    return {
        "payload": str(payload),
        "architecture": arch,
        "exe_sha256": sha256_file(exe),
        "exe_meta": exe_meta,
        "manifest": manifest,
        "forbidden": forbidden,
        "file_count": sum(1 for p in payload.rglob("*") if p.is_file()),
    }


def read_iss_text(root: Optional[Path] = None) -> str:
    path = iss_script_path(root)
    return path.read_text(encoding="utf-8")


def assert_iss_has_no_hardcoded_app_version(iss_text: str) -> None:
    if re.search(r'#\s*define\s+MyAppVersion\s+"', iss_text, re.IGNORECASE):
        raise InstallerAborted(
            "ISS enthaelt hart codiertes #define MyAppVersion (zweite Versionsquelle)."
        )
    if re.search(r'AppVersion\s*=\s*"0\.\d+\.\d+"', iss_text):
        raise InstallerAborted("ISS enthaelt hart codierte AppVersion.")


def metadata_defines() -> Dict[str, str]:
    """Werte fuer ISCC /D... – Source of Truth: app_info.py + stabile AppId."""
    if not APP_ID_STABLE:
        raise InstallerAborted("APP_ID_STABLE muss YES/True sein.")
    if not _GUID_RE.match(INNO_APP_ID_GUID):
        raise InstallerAborted("INNO_APP_ID_GUID ist keine gueltige GUID.")
    return {
        "MyAppName": APP_NAME,
        "MyAppVersion": APP_VERSION,
        "MyAppVersionInfo": WINDOWS_FILE_VERSION,
        "MyAppPublisher": WINDOWS_COMPANY_NAME or APP_AUTHOR,
        "MyAppURL": APP_WEBSITE_URL,
        "MyAppExeName": EXE_FILENAME,
        "MyAppId": INNO_APP_ID,
        "MyAppCopyright": APP_COPYRIGHT,
        "MyAppDescription": APP_DESCRIPTION,
    }


def defines_generated_path(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / DEFINES_GENERATED_REL


def _iss_escape(value: str) -> str:
    return value.replace('"', '""')


def write_defines_iss(root: Optional[Path] = None) -> Path:
    """Schreibe UTF-8-BOM Include mit Metadaten aus app_info.py."""
    path = defines_generated_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = metadata_defines()
    lines = [
        "; AUTO-GENERATED by build_tools/create_installer.py – do not edit.",
        "; Source of truth: app_info.py (+ stable AppId).",
        "",
    ]
    for key, value in values.items():
        lines.append(f'#define {key} "{_iss_escape(value)}"')
    lines.append("")
    # UTF-8 BOM for Inno Setup Unicode string safety (copyright / umlauts).
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    return path


def build_iscc_command_defines(
    *,
    payload_dir: Path,
    output_dir: Path,
    setup_icon: Path,
    defines_include: Path,
) -> List[str]:
    """Pfad-Defines + Include fuer UTF-8-Metadaten."""
    return [
        f"/DPayloadDir={_inno_path(payload_dir)}",
        f"/DOutputDir={_inno_path(output_dir)}",
        f"/DSetupIcon={_inno_path(setup_icon)}",
        f"/DMyAppDefinesInclude={_inno_path(defines_include)}",
    ]


def build_iscc_defines(
    *,
    payload_dir: Path,
    output_dir: Path,
    setup_icon: Path,
    extra: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Kompatibilitaets-Helfer: Metadaten + Pfade als /D (ASCII-sicher)."""
    values = metadata_defines()
    values["PayloadDir"] = _inno_path(payload_dir)
    values["OutputDir"] = _inno_path(output_dir)
    values["SetupIcon"] = _inno_path(setup_icon)
    if extra:
        values.update(extra)
    return [f"/D{key}={value}" for key, value in values.items()]


def _inno_path(path: Path) -> str:
    """Pfad ohne trailing backslash (ISCC-/D-Quoting-Fallen)."""
    text = str(path.resolve())
    while text.endswith(("\\", "/")) and len(text) > 3:
        text = text[:-1]
    return text


def user_settings_dir() -> Path:
    """AppData-Ordner der App (Safety Notice / Settings) – nie deinstallieren."""
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".nc-code-generator"


def parse_semver(version: str) -> Tuple[int, int, int]:
    """Numerisches major.minor.patch. Keine freien Strings."""
    derive_windows_version(version)
    parts = version.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])


def compare_semver(left: str, right: str) -> int:
    """-1 wenn left < right, 0 gleich, 1 wenn left > right."""
    a = parse_semver(left)
    b = parse_semver(right)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def downgrade_should_block(installed_version: str, setup_version: str) -> bool:
    return compare_semver(installed_version, setup_version) > 0


def version_guard_path(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / VERSION_GUARD_REL


def windows_release_asset_names(app_version: str = APP_VERSION) -> Dict[str, str]:
    derive_windows_version(app_version)
    folder = f"NC-Code-Generator_{app_version}_Windows_x64"
    setup = installer_filename(app_version)
    return {
        "folder": folder,
        "zip": f"{folder}.zip",
        "zip_sha256": f"{folder}.zip.sha256",
        "setup": setup,
        "setup_sha256": f"{setup}.sha256",
        "sums": "SHA256SUMS.txt",
        "manifest": "release_manifest.json",
    }


def write_named_sha256(path: Path) -> Tuple[Path, str]:
    digest = sha256_file(path)
    sidecar = Path(str(path) + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return sidecar, digest


def verify_named_sha256(path: Path, sidecar: Path) -> str:
    text = sidecar.read_text(encoding="utf-8")
    listed = text.strip().split()
    if not listed:
        raise InstallerAborted("SHA256-Sidecar leer.")
    expected = listed[0].lower()
    actual = sha256_file(path)
    if actual != expected:
        raise InstallerAborted(f"SHA256-Sidecar stimmt nicht: {path.name}")
    if path.name not in text:
        raise InstallerAborted(f"SHA256-Sidecar ohne Dateiname: {path.name}")
    if "/" in text or "\\" in text.split(None, 1)[-1]:
        raise InstallerAborted("SHA256-Sidecar darf keine Pfade enthalten.")
    return actual


def write_asset_sha256sums(files: List[Path], dest: Path) -> Path:
    """Deterministische SHA256SUMS (nur Dateinamen, sortiert)."""
    rows: List[Tuple[str, str]] = []
    for path in files:
        if not path.is_file():
            raise InstallerAborted(f"SHA256SUMS: Datei fehlt: {path.name}")
        rows.append((path.name, sha256_file(path)))
    rows.sort(key=lambda item: item[0].lower())
    text = "\n".join(f"{digest}  {name}" for name, digest in rows) + "\n"
    dest.write_text(text, encoding="utf-8")
    return dest


def verify_asset_sha256sums(files: List[Path], sums_path: Path) -> None:
    if not sums_path.is_file():
        raise InstallerAborted("SHA256SUMS.txt fehlt.")
    listed: Dict[str, str] = {}
    for raw in sums_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        digest, name = line.split("  ", 1)
        if "/" in name or "\\" in name:
            raise InstallerAborted("SHA256SUMS enthaelt Pfade.")
        listed[name] = digest.lower()
    expected: Dict[str, str] = {}
    for path in files:
        expected[path.name] = sha256_file(path)
    if listed != expected:
        raise InstallerAborted("SHA256SUMS stimmt nicht mit den Artefakten ueberein.")


def start_menu_shortcut_path(app_name: str = APP_NAME) -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / f"{app_name}.lnk"
    )


def desktop_shortcut_path(app_name: str = APP_NAME) -> Path:
    home = Path.home()
    return home / "Desktop" / f"{app_name}.lnk"


def git_tree_hash(root: Optional[Path] = None) -> Optional[str]:
    base = root or project_root()
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(base),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip() or None


def assert_no_absolute_paths(blob: str) -> None:
    collapsed = blob.replace("/", "\\").replace("\\\\", "\\").lower()
    if "e:\\jens\\" in collapsed or "c:\\users\\" in collapsed:
        raise InstallerAborted("Release-Manifest enthaelt private absolute Pfade.")


def release_paths_exist(root: Path, app_version: str) -> bool:
    names = windows_release_asset_names(app_version)
    release_root = root / "release"
    zip_path = release_root / names["zip"]
    folder = release_root / names["folder"]
    return zip_path.is_file() or folder.is_dir()
