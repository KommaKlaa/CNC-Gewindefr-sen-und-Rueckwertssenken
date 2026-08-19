"""Isolierte Mini-Installer fuer Upgrade-/Downgrade-Tests (nicht produktiv)."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from typing import Optional

from installer_config import (
    TEST_APP_ID,
    InstallerAborted,
    require_iscc,
    setup_icon_path,
    version_guard_path,
)
from release_packaging import project_root


def write_mini_payload(dest: Path, marker: bytes) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "NC-Code-Generator.exe").write_bytes(marker)
    (dest / "runtime.dll").write_bytes(b"dll-" + marker)
    assets = dest / "assets"
    assets.mkdir(exist_ok=True)
    icon = setup_icon_path()
    (assets / "app_icon.ico").write_bytes(icon.read_bytes())
    return dest


def write_mini_iss(dest: Path, *, version: str, payload: Path, output_dir: Path) -> Path:
    guard = version_guard_path().name
    # Copy guard next to generated ISS so #include resolves without source paths in tests.
    (dest.parent / guard).write_text(
        version_guard_path().read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    payload_s = str(payload).replace("\\", "\\\\")
    output_s = str(output_dir).replace("\\", "\\\\")
    icon_s = str(setup_icon_path()).replace("\\", "\\\\")
    text = textwrap.dedent(
        f"""
        #define MyAppName "NC-Code Generator"
        #define MyAppVersion "{version}"
        #define MyAppVersionInfo "{version}.0"
        #define MyAppPublisher "Jens Behm"
        #define MyAppURL "https://behm-it.de"
        #define MyAppExeName "NC-Code-Generator.exe"
        #define MyAppId "{TEST_APP_ID}"
        #define MyAppCopyright "Test"
        #define MyAppDescription "Mini installer test"
        #define PayloadDir "{payload_s}"
        #define OutputDir "{output_s}"
        #define SetupIcon "{icon_s}"

        [Setup]
        AppId={{#MyAppId}}
        AppName={{#MyAppName}}
        AppVersion={{#MyAppVersion}}
        AppPublisher={{#MyAppPublisher}}
        DefaultDirName={{autopf}}\\NC-Code Generator MiniTest
        PrivilegesRequired=admin
        PrivilegesRequiredOverridesAllowed=commandline
        ArchitecturesAllowed=x64compatible
        ArchitecturesInstallIn64BitMode=x64compatible
        OutputDir={{#OutputDir}}
        OutputBaseFilename=Mini-Setup-{version}
        SetupIconFile={{#SetupIcon}}
        Compression=lzma
        SolidCompression=yes
        UninstallDisplayName={{#MyAppName}}
        UsePreviousAppDir=yes

        [Files]
        Source: "{{#PayloadDir}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

        [Icons]
        Name: "{{autoprograms}}\\NC-Code Generator MiniTest"; Filename: "{{app}}\\{{#MyAppExeName}}"

        #include "{guard}"
        """
    ).strip() + "\n"
    dest.write_text(text, encoding="utf-8")
    return dest


def compile_mini_setup(iss: Path, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    iscc = require_iscc()
    completed = subprocess.run(
        [str(iscc), str(iss)],
        cwd=str(cwd or iss.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise InstallerAborted(
            f"Mini-ISCC Exit {completed.returncode}\n{completed.stdout}\n{completed.stderr}"
        )
    return completed


def silent_setup_cmd(setup_exe: Path, install_dir: Path, tasks: str = "") -> list[str]:
    return [
        str(setup_exe),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/CURRENTUSER",
        f"/DIR={install_dir}",
        f"/TASKS={tasks}",
    ]


def project_icon() -> Path:
    return setup_icon_path(project_root())
