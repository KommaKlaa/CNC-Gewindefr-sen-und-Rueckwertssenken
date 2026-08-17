"""Erzeugt das portable Windows-Releasepaket aus dem Nuitka-Standalone-Dist."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "build_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "build_tools"))

from app_info import APP_NAME, APP_VERSION, BSF_REAL_TOOL_VALIDATED, EXE_FILENAME, WINDOWS_FILE_VERSION
from nuitka_standalone import dist_exe_path
from release_packaging import (
    ReleaseAborted,
    assert_clean_payload,
    assert_docs_match_app_info,
    assert_exe_matches_app_info,
    assert_release_paths,
    assert_zip_top_level,
    confirm_release_architecture,
    copy_dist,
    create_zip,
    dir_size,
    git_info,
    load_build_manifest,
    project_root,
    python_architecture,
    release_folder_name,
    remove_tree,
    require_dist,
    scan_forbidden,
    sha256_file,
    source_fingerprint,
    verify_sha256sums,
    verify_zip_sha256,
    windows_platform_tag,
    write_build_manifest,
    write_release_docs,
    write_sha256sums,
    write_zip_sha256,
)


def _run_pytest(root: Path) -> None:
    print("=== Tests ===")
    completed = subprocess.run([sys.executable, "-m", "pytest"], cwd=str(root))
    if completed.returncode != 0:
        raise ReleaseAborted("TEST_GATE FAIL / BUILD ABORT")


def _run_nuitka(root: Path) -> None:
    print("=== Nuitka standalone ===")
    script = root / "build_tools" / "nuitka_standalone.py"
    completed = subprocess.run([sys.executable, str(script)], cwd=str(root))
    if completed.returncode != 0:
        raise ReleaseAborted("NUITKA BUILD FAIL")


def _dist_matches_source(root: Path, exe: Path) -> bool:
    manifest_path = root / "build" / "build_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if manifest.get("app_version") != APP_VERSION:
        return False
    if manifest.get("windows_file_version") != WINDOWS_FILE_VERSION:
        return False
    if manifest.get("source_fingerprint") != source_fingerprint(root):
        return False
    if not exe.is_file():
        return False
    return True


def _run_smoke(exe: Path, label: str) -> Dict[str, object]:
    print(f"=== Runtime-Smoke ({label}) ===")
    report = Path(tempfile.gettempdir()) / f"nc_generator_release_smoke_{label}.json"
    if report.exists():
        report.unlink()
    env = os.environ.copy()
    env["NC_GENERATOR_RUNTIME_SMOKE"] = "1"
    env["NC_GENERATOR_SMOKE_REPORT"] = str(report)
    cwd = Path(tempfile.gettempdir())
    try:
        completed = subprocess.run(
            [str(exe)],
            cwd=str(cwd),
            env=env,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReleaseAborted(f"Smoke-Timeout ({label})") from exc
    if completed.returncode != 0:
        extra = ""
        if report.is_file():
            extra = "\n" + report.read_text(encoding="utf-8")
        raise ReleaseAborted(f"Smoke Exit {completed.returncode} ({label}){extra}")
    if not report.is_file():
        raise ReleaseAborted(f"Smoke-Report fehlt ({label})")
    data = json.loads(report.read_text(encoding="utf-8"))
    if not data.get("ok"):
        raise ReleaseAborted(f"Smoke-Report nicht ok ({label}): {data.get('errors')}")
    if data.get("app") != APP_NAME or data.get("version") != APP_VERSION:
        raise ReleaseAborted("Info-/App-Version im Smoke weicht von app_info.py ab.")
    bgf = data.get("steps", {}).get("bgf_nc") or {}
    if str(bgf.get("snippet_ok")) != "True":
        raise ReleaseAborted(f"BGF-Smoke fehlgeschlagen ({label}): {bgf}")
    bsf = data.get("steps", {}).get("bsf_nc") or {}
    if str(bsf.get("has_begin")) != "True":
        raise ReleaseAborted(f"BSF-Smoke fehlgeschlagen ({label}): {bsf}")
    if not data.get("steps", {}).get("heidenhain_h"):
        raise ReleaseAborted(f".H-Export-Smoke fehlgeschlagen ({label})")
    return data


def _extract_and_smoke(zip_path: Path, folder_name: str) -> Dict[str, object]:
    tmp = Path(tempfile.mkdtemp(prefix="nc_release_unzip_"))
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(tmp)
    extracted = tmp / folder_name
    exe = extracted / EXE_FILENAME
    if not exe.is_file():
        raise ReleaseAborted(f"Entpackte EXE fehlt: {exe}")
    return _run_smoke(exe, "extracted_zip")


def package_from_dist(root: Path) -> Dict[str, object]:
    dist_exe = dist_exe_path(root)
    dist = dist_exe.parent
    require_dist(dist, dist_exe)
    arch = confirm_release_architecture(dist_exe)
    exe_meta = assert_exe_matches_app_info(dist_exe)
    folder_name = release_folder_name(APP_VERSION, windows_platform_tag(arch))
    release_root = root / "release"
    release_root.mkdir(parents=True, exist_ok=True)
    dest = release_root / folder_name
    zip_path = release_root / f"{folder_name}.zip"
    assert_release_paths(dest, zip_path, root)

    if dest.exists():
        print(f"Entferne vorherigen Releaseordner {dest.name}")
        remove_tree(dest)
    if zip_path.exists():
        zip_path.unlink()
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    if sidecar.exists():
        sidecar.unlink()

    copy_dist(dist, dest)
    manifest = load_build_manifest(root)
    write_release_docs(dest, root / "CHANGELOG.md", manifest)
    assert_docs_match_app_info(dest)
    assert_clean_payload(dest)
    write_sha256sums(dest)
    verify_sha256sums(dest)

    create_zip(dest, zip_path, folder_name)
    assert_zip_top_level(zip_path, folder_name)
    sidecar, zip_digest = write_zip_sha256(zip_path)
    verified = verify_zip_sha256(zip_path, sidecar)
    if verified != zip_digest:
        raise ReleaseAborted("ZIP-Hash intern inkonsistent.")

    exe_release = dest / EXE_FILENAME
    if not exe_release.is_file():
        raise ReleaseAborted("EXE fehlt im Releaseordner.")
    exe_sha = sha256_file(exe_release)
    forbidden = scan_forbidden(dest)
    return {
        "release_dir": str(dest),
        "zip_path": str(zip_path),
        "folder_name": folder_name,
        "architecture": arch,
        "exe_sha256": exe_sha,
        "zip_sha256": verified,
        "file_count": sum(1 for p in dest.rglob("*") if p.is_file()),
        "dist_size": dir_size(dist),
        "zip_size": zip_path.stat().st_size,
        "exe_size": exe_release.stat().st_size,
        "source_py": forbidden["source"],
        "dev_files": forbidden["dev"],
        "user_files": forbidden["user"],
        "exe_meta": exe_meta,
        "manifest": manifest,
    }


def run_release(argv: Optional[List[str]] = None) -> Dict[str, object]:
    parser = argparse.ArgumentParser(description="Portables Nuitka-Standalone-Release erzeugen.")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-build", action="store_true", help="Dist wiederverwenden, auch ohne Fingerprint-Match.")
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    root = project_root()
    git = git_info(root)
    if git.get("git_available") and git.get("git_dirty") and not args.allow_dirty:
        raise ReleaseAborted("Working Tree ist dirty. Release blockiert (kein --allow-dirty).")

    if not args.skip_tests:
        _run_pytest(root)

    exe = dist_exe_path(root)
    rebuilt = False
    reused = False
    if args.force_build or not args.skip_build:
        if args.force_build or not _dist_matches_source(root, exe):
            _run_nuitka(root)
            rebuilt = True
        else:
            reused = True
            print("Nuitka-Dist entspricht aktuellem Source-Fingerprint, Build wird wiederverwendet.")
    else:
        reused = True
        print("Nuitka-Build laut --skip-build wiederverwendet.")

    require_dist(exe.parent, exe)
    write_build_manifest(root, exe, console=False)

    if not args.skip_smoke:
        _run_smoke(exe, "dist")

    result = package_from_dist(root)
    result["nuitka_build_reused_or_rebuilt"] = "REBUILT" if rebuilt else "REUSED"
    result["dist_source"] = str(exe.parent)
    result["git"] = git

    if not args.skip_smoke:
        result["release_smoke"] = _run_smoke(Path(result["release_dir"]) / EXE_FILENAME, "release_folder")
        result["zip_smoke"] = _extract_and_smoke(Path(result["zip_path"]), result["folder_name"])

    print(f"RELEASE_DIR={result['release_dir']}")
    print(f"ZIP_PATH={result['zip_path']}")
    print(f"EXE_SHA256={result['exe_sha256']}")
    print(f"ZIP_SHA256={result['zip_sha256']}")
    print("RELEASE OK")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    try:
        run_release(argv)
    except ReleaseAborted as exc:
        print("RELEASE ABORTED")
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
