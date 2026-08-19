"""INSTALLER.2 – isolierte Mini-Setup Upgrade/Same/Downgrade/Uninstall-Tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))

from installer_config import (
    TEST_APP_ID_GUID,
    find_iscc,
)
from installer_minitest import (
    compile_mini_setup,
    silent_setup_cmd,
    write_mini_iss,
    write_mini_payload,
)
from release_packaging import sha256_file as packaging_sha256


def _uninstall_key():
    # Inno stores AppId={{GUID}} as uninstall key '{GUID}}' (escaped braces).
    return (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{"
        + TEST_APP_ID_GUID
        + r"}}_is1"
    )


def _query_uninstall(name: str):
    key_path = _uninstall_key()
    hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)
    for hive in hives:
        for view in views:
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    return value
            except OSError:
                continue
    return None


@unittest.skipUnless(find_iscc() is not None, "INNO_SETUP_NOT_FOUND")
class TestMiniInstallerUpgradeMatrix(unittest.TestCase):
    def test_upgrade_same_downgrade_uninstall(self):
        settings_dir = Path(os.environ.get("APPDATA", "")) / "NC-Code Generator"
        settings_dir.mkdir(parents=True, exist_ok=True)
        sentinel = settings_dir / "installer2_user_data_probe.json"
        sentinel.write_text('{"probe":"INSTALLER.2","keep":true}\n', encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="nc_mini_iss_") as tmp:
            tmp_path = Path(tmp)
            payload_a = write_mini_payload(tmp_path / "payload_a", b"MARKER-A")
            payload_b = write_mini_payload(tmp_path / "payload_b", b"MARKER-B")
            out_a = tmp_path / "out_a"
            out_b = tmp_path / "out_b"
            out_a.mkdir()
            out_b.mkdir()
            iss_dir = tmp_path / "iss"
            iss_dir.mkdir()
            iss_a = write_mini_iss(
                iss_dir / "mini_a.iss",
                version="9.9.8",
                payload=payload_a,
                output_dir=out_a,
            )
            iss_b = write_mini_iss(
                iss_dir / "mini_b.iss",
                version="9.9.9",
                payload=payload_b,
                output_dir=out_b,
            )
            compile_mini_setup(iss_a)
            compile_mini_setup(iss_b)
            setup_a = out_a / "Mini-Setup-9.9.8.exe"
            setup_b = out_b / "Mini-Setup-9.9.9.exe"
            self.assertTrue(setup_a.is_file())
            self.assertTrue(setup_b.is_file())

            install_dir = tmp_path / "app"
            install_dir.mkdir()
            exe = install_dir / "NC-Code-Generator.exe"

            def install(setup: Path) -> subprocess.CompletedProcess:
                return subprocess.run(
                    silent_setup_cmd(setup, install_dir),
                    timeout=180,
                )

            def uninstall() -> None:
                unins = sorted(install_dir.glob("unins*.exe"))
                if not unins:
                    return
                subprocess.run(
                    [str(unins[0]), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    timeout=180,
                )
                for _ in range(40):
                    if not exe.is_file():
                        break
                    time.sleep(0.2)

            try:
                first = install(setup_a)
                self.assertEqual(first.returncode, 0, "Upgrade-Basis 9.9.8 muss installieren.")
                self.assertTrue(exe.is_file())
                self.assertEqual(exe.read_bytes(), b"MARKER-A")
                hash_a = packaging_sha256(exe)
                self.assertEqual(_query_uninstall("DisplayVersion"), "9.9.8")
                loc = _query_uninstall("InstallLocation")
                self.assertTrue(loc)
                self.assertIsNotNone(_query_uninstall("UninstallString"))

                upgrade = install(setup_b)
                self.assertEqual(upgrade.returncode, 0, "Upgrade 9.9.8 -> 9.9.9 muss PASS sein.")
                self.assertEqual(exe.read_bytes(), b"MARKER-B")
                hash_b = packaging_sha256(exe)
                self.assertNotEqual(hash_a, hash_b)
                self.assertEqual(_query_uninstall("DisplayVersion"), "9.9.9")
                loc_after = _query_uninstall("InstallLocation")
                self.assertEqual(loc, loc_after)
                self.assertEqual(len(list(install_dir.glob("unins*.exe"))), 1)

                same = install(setup_b)
                self.assertEqual(same.returncode, 0, "Same-version reinstall muss PASS sein.")
                self.assertEqual(packaging_sha256(exe), hash_b)

                blocked = install(setup_a)
                self.assertNotEqual(blocked.returncode, 0, "Downgrade muss blockieren.")
                self.assertEqual(exe.read_bytes(), b"MARKER-B")
                self.assertEqual(packaging_sha256(exe), hash_b)
                self.assertEqual(_query_uninstall("DisplayVersion"), "9.9.9")

                start_menu = (
                    Path(os.environ.get("APPDATA", ""))
                    / "Microsoft"
                    / "Windows"
                    / "Start Menu"
                    / "Programs"
                    / "NC-Code Generator MiniTest.lnk"
                )
                self.assertTrue(start_menu.is_file())
                uninstall()
                self.assertFalse(exe.is_file())
                self.assertIsNone(_query_uninstall("UninstallString"))
                self.assertTrue(sentinel.is_file())
            finally:
                uninstall()
                self.assertTrue(sentinel.is_file())


if __name__ == "__main__":
    unittest.main()
