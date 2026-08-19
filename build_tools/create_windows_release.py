"""Orchestriert Nuitka + portable ZIP + Setup (genau ein Nuitka-Build).

Kein zweiter Nuitka-Lauf im Installer.
v0.1.3-Artefakte werden ohne --overwrite nicht angefasst.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "build_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "build_tools"))

from app_info import APP_VERSION, EXE_FILENAME, WINDOWS_FILE_VERSION
from create_installer import run_installer
from create_release import (
    _dist_matches_source,
    _run_nuitka,
    _run_pytest,
    _run_smoke,
    package_from_dist,
)
from installer_config import (
    CODE_SIGNING,
    InstallerAborted,
    assert_no_absolute_paths,
    git_tree_hash,
    installer_filename,
    installer_output_dir,
    release_paths_exist,
    source_fingerprint,
    validate_installer_payload,
    verify_asset_sha256sums,
    verify_installer_sha256,
    verify_named_sha256,
    windows_release_asset_names,
    write_asset_sha256sums,
)
from nuitka_standalone import dist_exe_path
from release_packaging import (
    ReleaseAborted,
    git_info,
    project_root,
    require_dist,
    sha256_file as packaging_sha256,
    verify_zip_sha256,
    write_build_manifest,
)

WindowsReleaseAborted = InstallerAborted


def _nuitka_once(root: Path, counter: List[int]) -> None:
    if counter[0] >= 1:
        raise WindowsReleaseAborted("NUITKA_BUILD_COUNT > 1")
    _run_nuitka(root)
    counter[0] += 1


def write_windows_release_manifest(
    dest: Path,
    payload: Dict[str, object],
) -> Path:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert_no_absolute_paths(text)
    dest.write_text(text, encoding="utf-8")
    return dest


def run_windows_release(
    argv: Optional[List[str]] = None,
    *,
    nuitka_runner: Optional[Callable[[Path], None]] = None,
) -> Dict[str, object]:
    parser = argparse.ArgumentParser(
        description="Windows-Release: Tests, ein Nuitka-Build, ZIP, Setup, Hashes."
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-install-smoke", action="store_true")
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="Portables ZIP/Ordner nicht neu erzeugen (existierende Artefakte nutzen).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Existierende portable Release-Artefakte ersetzen. Niemals fuer eingefrorene Releases.",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    root = project_root()
    git = git_info(root)
    if git.get("git_available") and git.get("git_dirty") and not args.allow_dirty:
        raise WindowsReleaseAborted("Working Tree ist dirty. Windows-Release blockiert.")

    names = windows_release_asset_names(APP_VERSION)
    release_root = root / "release"
    zip_path = release_root / names["zip"]
    folder = release_root / names["folder"]

    if (not args.skip_package) and release_paths_exist(root, APP_VERSION) and not args.overwrite:
        raise WindowsReleaseAborted(
            "OVERWRITE_BLOCKED: portable Release-Artefakte existieren bereits. "
            "Kein Ueberschreiben (v0.1.3 einfrieren). --skip-package oder --overwrite."
        )

    test_result = "skipped"
    if not args.skip_tests:
        _run_pytest(root)
        test_result = "pytest passed"

    nuitka_count = [0]

    def run_nuitka(path: Path) -> None:
        if nuitka_runner is not None:
            if nuitka_count[0] >= 1:
                raise WindowsReleaseAborted("NUITKA_BUILD_COUNT > 1")
            nuitka_runner(path)
            nuitka_count[0] += 1
        else:
            _nuitka_once(path, nuitka_count)

    exe = dist_exe_path(root)
    if args.force_build:
        run_nuitka(root)
        exe = dist_exe_path(root)
    elif not args.skip_build:
        if not _dist_matches_source(root, exe):
            run_nuitka(root)
            exe = dist_exe_path(root)

    if nuitka_count[0] > 1:
        raise WindowsReleaseAborted("NUITKA_BUILD_COUNT > 1")

    require_dist(exe.parent, exe)
    write_build_manifest(root, exe, console=False)
    dist_exe_sha = packaging_sha256(exe)

    if not args.skip_smoke:
        _run_smoke(exe, "dist")

    packaged: Optional[Dict[str, object]] = None
    if not args.skip_package:
        packaged = package_from_dist(root)
        zip_path = Path(packaged["zip_path"])
        folder = Path(packaged["release_dir"])

    if not folder.is_dir() or not zip_path.is_file():
        raise WindowsReleaseAborted("Portable Payload/ZIP fehlt.")

    payload_info = validate_installer_payload(root, folder)
    portable_exe_sha = str(payload_info["exe_sha256"])
    if portable_exe_sha != dist_exe_sha:
        raise WindowsReleaseAborted("DIST_EXE_SHA256 != PORTABLE_EXE_SHA256")

    installer_argv = [
        "--payload",
        str(folder),
        "--output-dir",
        str(installer_output_dir(root)),
    ]
    if args.allow_dirty:
        installer_argv.append("--allow-dirty")
    if args.skip_smoke or args.skip_install_smoke:
        installer_argv.append("--skip-install-smoke")

    installer_result = run_installer(installer_argv)
    setup_path = Path(str(installer_result["installer_path"]))
    setup_sidecar = Path(str(installer_result["installer_sha256_sidecar"]))
    zip_sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")

    zip_digest = verify_zip_sha256(zip_path, zip_sidecar)
    setup_digest = verify_installer_sha256(setup_path, setup_sidecar)

    sums_dir = release_root if not args.skip_package else installer_output_dir(root)
    sums_dir.mkdir(parents=True, exist_ok=True)

    staged_setup = setup_path
    staged_setup_sidecar = setup_sidecar
    if not args.skip_package:
        staged_setup = release_root / names["setup"]
        staged_setup_sidecar = release_root / names["setup_sha256"]
        if staged_setup.resolve() != setup_path.resolve():
            staged_setup.write_bytes(setup_path.read_bytes())
            staged_setup_sidecar.write_text(
                f"{setup_digest}  {staged_setup.name}\n",
                encoding="utf-8",
            )
        verify_named_sha256(staged_setup, staged_setup_sidecar)

    sums_path = sums_dir / names["sums"]
    write_asset_sha256sums([zip_path, staged_setup], sums_path)
    verify_asset_sha256sums([zip_path, staged_setup], sums_path)
    verify_named_sha256(zip_path, zip_sidecar)
    verify_named_sha256(staged_setup, staged_setup_sidecar)

    installed_sha = installer_result.get("installed_exe_sha256")
    if installed_sha and installed_sha != portable_exe_sha:
        raise WindowsReleaseAborted("INSTALLED_EXE_SHA256 != PORTABLE_EXE_SHA256")

    all_identical = dist_exe_sha == portable_exe_sha
    if installed_sha:
        all_identical = all_identical and installed_sha == portable_exe_sha

    manifest = {
        "app_version": APP_VERSION,
        "windows_version": WINDOWS_FILE_VERSION,
        "source_head": git.get("git_commit"),
        "source_tree": git_tree_hash(root),
        "source_fingerprint": source_fingerprint(root),
        "portable_zip_sha256": zip_digest,
        "installer_sha256": setup_digest,
        "payload_exe_sha256": portable_exe_sha,
        "dist_exe_sha256": dist_exe_sha,
        "test_result": test_result,
        "nuitka_build_count": nuitka_count[0],
        "code_signing": CODE_SIGNING,
        "exe_filename": EXE_FILENAME,
        "installer_filename": installer_filename(APP_VERSION),
        "zip_filename": names["zip"],
    }
    manifest_path = sums_dir / names["manifest"]
    write_windows_release_manifest(manifest_path, manifest)

    result: Dict[str, object] = {
        "app_version": APP_VERSION,
        "nuitka_build_count": nuitka_count[0],
        "dist_exe_sha256": dist_exe_sha,
        "portable_exe_sha256": portable_exe_sha,
        "installed_exe_sha256": installed_sha,
        "all_exe_hashes_identical": all_identical,
        "zip_path": str(zip_path),
        "zip_sha256": zip_digest,
        "installer_path": str(staged_setup),
        "installer_sha256": setup_digest,
        "sha256sums": str(sums_path),
        "manifest": str(manifest_path),
        "code_signing": CODE_SIGNING,
        "installer": installer_result,
        "packaged": packaged,
        "skip_package": args.skip_package,
    }
    print(f"NUITKA_BUILD_COUNT={nuitka_count[0]}")
    print(f"DIST_EXE_SHA256={dist_exe_sha}")
    print(f"PORTABLE_EXE_SHA256={portable_exe_sha}")
    print(f"INSTALLED_EXE_SHA256={installed_sha}")
    print(f"ALL_EXE_HASHES_IDENTICAL={all_identical}")
    print(f"ZIP_SHA256={zip_digest}")
    print(f"INSTALLER_SHA256={setup_digest}")
    print(f"CODE_SIGNING={CODE_SIGNING}")
    print("WINDOWS RELEASE OK")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    try:
        run_windows_release(argv)
    except (WindowsReleaseAborted, InstallerAborted, ReleaseAborted) as exc:
        print("WINDOWS RELEASE ABORTED")
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
