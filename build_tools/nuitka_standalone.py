"""Nuitka-Standalone-Kommando aus zentralen App-Metadaten."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app_info import (
    APP_COPYRIGHT,
    APP_DESCRIPTION,
    APP_NAME,
    DIST_FOLDER_NAME,
    EXE_FILENAME,
    WINDOWS_COMPANY_NAME,
    WINDOWS_FILE_VERSION,
    WINDOWS_PRODUCT_VERSION,
)
from app_paths import APP_ICON_ICO_REL

MAIN_SCRIPT = "bsf_generator_verbessert_v3.py"
OUTPUT_DIR = "build"
REPORT_PATH = "build/nuitka-compilation-report.xml"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def nuitka_command(*, console_mode: str = "disable") -> List[str]:
    if console_mode not in ("disable", "force", "attach", "hide"):
        raise ValueError(f"Ungueltiger Konsolenmodus: {console_mode}")
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        f"--windows-console-mode={console_mode}",
        f"--windows-icon-from-ico={APP_ICON_ICO_REL}",
        f"--output-filename={EXE_FILENAME}",
        f"--output-folder-name={DIST_FOLDER_NAME}",
        f"--output-dir={OUTPUT_DIR}",
        f"--product-name={APP_NAME}",
        f"--product-version={WINDOWS_PRODUCT_VERSION}",
        f"--file-version={WINDOWS_FILE_VERSION}",
        f"--file-description={APP_DESCRIPTION}",
        f"--copyright={APP_COPYRIGHT}",
        f"--company-name={WINDOWS_COMPANY_NAME}",
        "--include-data-dir=assets=assets",
        "--include-package=coordinates",
        "--include-package=preview",
        "--include-package=help_views",
        "--include-package=ui",
        "--enable-plugins=tk-inter",
        "--assume-yes-for-downloads",
        f"--report={REPORT_PATH}",
        MAIN_SCRIPT,
    ]


def dist_exe_path(root: Path | None = None) -> Path:
    base = root or project_root()
    return base / OUTPUT_DIR / f"{DIST_FOLDER_NAME}.dist" / EXE_FILENAME


def main() -> int:
    root = project_root()
    console = "force" if "--console" in sys.argv else "disable"
    cmd = nuitka_command(console_mode=console)
    print("Nuitka command:")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(root))
    if completed.returncode != 0:
        print("NUITKA BUILD FAIL")
        return completed.returncode
    exe = dist_exe_path(root)
    if not exe.is_file() or exe.stat().st_size <= 0:
        print(f"BUILD GATE FAIL: EXE fehlt oder leer: {exe}")
        return 1
    dist = exe.parent
    if not dist.is_dir():
        print(f"BUILD GATE FAIL: Dist-Ordner fehlt: {dist}")
        return 1
    print(f"EXE_PATH={exe}")
    print(f"DIST_PATH={dist}")
    print(f"EXE_SIZE={exe.stat().st_size}")
    from release_packaging import write_build_manifest

    manifest = write_build_manifest(root, exe, console=(console != "disable"))
    print(f"BUILD_MANIFEST={manifest}")
    print("BUILD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
