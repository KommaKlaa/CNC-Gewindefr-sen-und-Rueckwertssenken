"""Erzeugt den Windows-Installer aus dem bereits geprueften Nuitka-Payload.

Kein zweiter Nuitka-Build. Portable ZIP bleibt unveraendert.
Inno Setup kompiliert denselben Standalone-Bestand wie das ZIP.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "build_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "build_tools"))

from app_info import APP_NAME, APP_VERSION, EXE_FILENAME
from installer_config import (
    INNO_SETUP_NOT_FOUND,
    InstallerAborted,
    assert_iss_has_no_hardcoded_app_version,
    build_iscc_command_defines,
    installer_filename,
    installer_output_dir,
    iscc_version_label,
    iss_script_path,
    read_iss_text,
    require_iscc,
    resolve_payload_dir,
    setup_icon_path,
    user_settings_dir,
    validate_installer_payload,
    verify_installer_sha256,
    write_defines_iss,
    write_installer_sha256,
)
from release_packaging import git_info, project_root, remove_tree, sha256_file


def _run_exe_smoke(exe: Path, label: str) -> Dict[str, object]:
    print(f"=== Runtime-Smoke ({label}) ===")
    report = Path(tempfile.gettempdir()) / f"nc_generator_installer_smoke_{label}.json"
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
        raise InstallerAborted(f"Smoke-Timeout ({label})") from exc
    if completed.returncode != 0:
        extra = ""
        if report.is_file():
            extra = "\n" + report.read_text(encoding="utf-8")
        raise InstallerAborted(f"Smoke Exit {completed.returncode} ({label}){extra}")
    if not report.is_file():
        raise InstallerAborted(f"Smoke-Report fehlt ({label})")
    data = json.loads(report.read_text(encoding="utf-8"))
    if not data.get("ok"):
        raise InstallerAborted(f"Smoke-Report nicht ok ({label}): {data.get('errors')}")
    if data.get("app") != APP_NAME or data.get("version") != APP_VERSION:
        raise InstallerAborted("App-Version im Smoke weicht von app_info.py ab.")
    hpr = data.get("steps", {}).get("hpr5000_m16") or {}
    if str(hpr.get("machining_z")) != "True":
        raise InstallerAborted(f"HPR5000-M16-Smoke fehlgeschlagen ({label}): {hpr}")
    stale = data.get("steps", {}).get("nc_stale") or {}
    if str(stale.get("export_pass")) != "True":
        raise InstallerAborted(f"Stale-NC-Smoke fehlgeschlagen ({label}): {stale}")
    return data


def _compile_installer(
    *,
    root: Path,
    iscc: Path,
    payload: Path,
    output_dir: Path,
) -> Dict[str, object]:
    iss = iss_script_path(root)
    if not iss.is_file():
        raise InstallerAborted(f"ISS fehlt: {iss}")
    assert_iss_has_no_hardcoded_app_version(read_iss_text(root))

    icon = setup_icon_path(root)
    if not icon.is_file():
        raise InstallerAborted(f"Setup-Icon fehlt: {icon}")

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / installer_filename()
    sidecar = output_dir / f"{installer_filename()}.sha256"
    if target.exists():
        target.unlink()
    if sidecar.exists():
        sidecar.unlink()

    defines_include = write_defines_iss(root)
    defines = build_iscc_command_defines(
        payload_dir=payload,
        output_dir=output_dir,
        setup_icon=icon,
        defines_include=defines_include,
    )
    cmd = [str(iscc), *defines, str(iss)]
    print("=== Inno Setup compile ===")
    print(" ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    if completed.returncode != 0:
        raise InstallerAborted(f"ISCC Exit {completed.returncode}")
    if not target.is_file() or target.stat().st_size <= 0:
        raise InstallerAborted(f"Installer-Output fehlt: {target}")
    engine = None
    blob = (completed.stdout or "") + "\n" + (completed.stderr or "")
    for line in blob.splitlines():
        if line.strip().lower().startswith("compiler engine version:"):
            engine = line.split(":", 1)[1].strip()
            break
    target_meta = {"path": target, "inno_engine": engine}
    return target_meta


def _find_uninstaller(install_dir: Path) -> Path:
    candidates = sorted(install_dir.glob("unins*.exe"))
    if not candidates:
        raise InstallerAborted(f"Uninstaller fehlt in {install_dir}")
    return candidates[0]


def _run_setup(
    setup_exe: Path,
    install_dir: Path,
    *,
    tasks: str = "",
) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(setup_exe),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/CURRENTUSER",
        f"/DIR={install_dir}",
        f"/TASKS={tasks}",
    ]
    print("=== Silent install ===")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, timeout=300)
    if completed.returncode != 0:
        raise InstallerAborted(f"Setup Exit {completed.returncode}")


def _run_uninstall(install_dir: Path) -> None:
    unins = _find_uninstaller(install_dir)
    cmd = [str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    print("=== Silent uninstall ===")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, timeout=300)
    if completed.returncode != 0:
        raise InstallerAborted(f"Uninstall Exit {completed.returncode}")
    # Inno copies uninstaller to TEMP; wait for directory cleanup.
    for _ in range(40):
        if not install_dir.exists():
            break
        remaining = [p for p in install_dir.rglob("*") if p.is_file()]
        if not remaining:
            break
        time.sleep(0.25)


def _smoke_install_cycle(
    setup_exe: Path,
    payload_exe_sha256: str,
) -> Dict[str, object]:
    settings_dir = user_settings_dir()
    settings_dir.mkdir(parents=True, exist_ok=True)
    sentinel = settings_dir / "installer1_user_data_probe.json"
    sentinel.write_text(
        '{"probe":"INSTALLER.1","keep":true}\n',
        encoding="utf-8",
    )

    tmp_root = Path(tempfile.mkdtemp(prefix="nc_installer_smoke_"))
    install_dir = tmp_root / "app"
    result: Dict[str, object] = {
        "install_dir": str(install_dir),
        "sentinel": str(sentinel),
    }
    try:
        _run_setup(setup_exe, install_dir)
        installed_exe = install_dir / EXE_FILENAME
        if not installed_exe.is_file():
            raise InstallerAborted("Installierte EXE fehlt.")
        has_python_dll = (install_dir / "python311.dll").is_file() or bool(
            list(install_dir.glob("python3*.dll"))
        )
        if not has_python_dll:
            raise InstallerAborted("Runtime-DLL fehlt nach Installation.")
        if not (install_dir / "assets" / "app_icon.ico").is_file():
            raise InstallerAborted("assets/app_icon.ico fehlt nach Installation.")

        installed_sha = sha256_file(installed_exe)
        result["installed_exe_sha256"] = installed_sha
        result["exe_hash_identical"] = installed_sha == payload_exe_sha256
        if installed_sha != payload_exe_sha256:
            raise InstallerAborted(
                "Installierte EXE weicht vom Payload-Hash ab "
                "(Installer darf Binaerdatei nicht aendern)."
            )

        smoke = _run_exe_smoke(installed_exe, "installed")
        result["install_runtime_smoke"] = smoke

        # Upgrade infrastructure: second install over the first with same AppId.
        _run_setup(setup_exe, install_dir)
        uninstallers = list(install_dir.glob("unins*.exe"))
        result["upgrade_uninstaller_count"] = len(uninstallers)
        if len(uninstallers) != 1:
            raise InstallerAborted(
                f"Upgrade-Infrastruktur: erwartete 1 Uninstaller-Datei, "
                f"gefunden {len(uninstallers)}"
            )
        if sha256_file(install_dir / EXE_FILENAME) != payload_exe_sha256:
            raise InstallerAborted("EXE-Hash nach Upgrade abweichend.")
        result["upgrade_infrastructure"] = "PASS"

        start_menu = (
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / f"{APP_NAME}.lnk"
        )
        result["start_menu_before_uninstall"] = start_menu.is_file()

        _run_uninstall(install_dir)
        still_there = install_dir.exists() and any(install_dir.rglob(EXE_FILENAME))
        result["app_program_files_removed"] = not still_there
        if still_there:
            raise InstallerAborted("Programmdateien nach Uninstall noch vorhanden.")

        result["start_menu_removed_after_uninstall"] = not start_menu.is_file()
        result["user_settings_preserved_after_uninstall"] = sentinel.is_file()
        if not sentinel.is_file():
            raise InstallerAborted("Benutzerdaten wurden bei Uninstall geloescht.")
        result["uninstall_test"] = "PASS"
    finally:
        # Keep sentinel on purpose (user-data probe). Clean install temp only.
        if tmp_root.exists():
            try:
                remove_tree(tmp_root)
            except OSError:
                pass
    return result


def run_installer(argv: Optional[List[str]] = None) -> Dict[str, object]:
    parser = argparse.ArgumentParser(
        description="Windows-Installer aus geprueftem Nuitka-Standalone-Payload erzeugen."
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=None,
        help="Pfad zum Release-/Dist-Ordner (Standard: release/... oder Nuitka-Dist).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Ausgabeordner (Standard: installer/output).",
    )
    parser.add_argument(
        "--skip-install-smoke",
        action="store_true",
        help="Keine silent Install/Uninstall-Smokes.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Dirty Working Tree erlauben.",
    )
    args = parser.parse_args(argv)

    root = project_root()
    git = git_info(root)
    if git.get("git_available") and git.get("git_dirty") and not args.allow_dirty:
        raise InstallerAborted("Working Tree ist dirty. Installer-Build blockiert.")

    iscc = require_iscc()
    iscc_label = iscc_version_label(iscc)

    payload = resolve_payload_dir(root, args.payload)
    validation = validate_installer_payload(root, payload)
    payload_exe_sha = str(validation["exe_sha256"])

    output_dir = (args.output_dir or installer_output_dir(root)).resolve()
    compiled = _compile_installer(
        root=root,
        iscc=iscc,
        payload=payload,
        output_dir=output_dir,
    )
    installer_path = compiled["path"]
    if compiled.get("inno_engine"):
        iscc_label = str(compiled["inno_engine"])
    sidecar, digest = write_installer_sha256(installer_path)
    verified = verify_installer_sha256(installer_path, sidecar)
    if verified != digest:
        raise InstallerAborted("Installer-Hash intern inkonsistent.")

    result: Dict[str, object] = {
        "installer_path": str(installer_path),
        "installer_size": installer_path.stat().st_size,
        "installer_sha256": digest,
        "installer_sha256_sidecar": str(sidecar),
        "inno_compiler": str(iscc),
        "inno_setup_version": iscc_label,
        "app_version": APP_VERSION,
        "payload": str(payload),
        "payload_exe_sha256": payload_exe_sha,
        "payload_validation": {
            "architecture": validation["architecture"],
            "file_count": validation["file_count"],
            "source_files": validation["forbidden"]["source"],
            "user_files": validation["forbidden"]["user"],
        },
        "git": git,
    }

    if not args.skip_install_smoke:
        smoke = _smoke_install_cycle(installer_path, payload_exe_sha)
        result["install_smoke"] = smoke
        result["installed_exe_sha256"] = smoke.get("installed_exe_sha256")
        result["exe_hash_identical"] = smoke.get("exe_hash_identical")

    print(f"INSTALLER_PATH={result['installer_path']}")
    print(f"INSTALLER_SIZE={result['installer_size']}")
    print(f"INSTALLER_SHA256={result['installer_sha256']}")
    print(f"INNO_COMPILER={result['inno_compiler']}")
    print(f"APP_VERSION={result['app_version']}")
    print(f"PAYLOAD_EXE_SHA256={result['payload_exe_sha256']}")
    if "installed_exe_sha256" in result:
        print(f"INSTALLED_EXE_SHA256={result['installed_exe_sha256']}")
        print(f"EXE_HASH_IDENTICAL={result['exe_hash_identical']}")
    print("INSTALLER OK")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    try:
        run_installer(argv)
    except InstallerAborted as exc:
        message = str(exc)
        print("INSTALLER ABORTED")
        print(message)
        if message != INNO_SETUP_NOT_FOUND and INNO_SETUP_NOT_FOUND in message:
            print(INNO_SETUP_NOT_FOUND)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
