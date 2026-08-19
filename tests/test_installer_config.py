"""INSTALLER.1 – ISS-/AppId-/Metadaten-Konfiguration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))

from app_info import (
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    APP_WEBSITE_URL,
    EXE_FILENAME,
    WINDOWS_COMPANY_NAME,
    WINDOWS_FILE_VERSION,
)
from app_paths import APP_ICON_ICO_REL
from installer_config import (
    APP_ID_STABLE,
    DEFAULT_INSTALL_DIR_INNO,
    INNO_APP_ID,
    INNO_APP_ID_GUID,
    assert_iss_has_no_hardcoded_app_version,
    installer_filename,
    iss_script_path,
    metadata_defines,
    read_iss_text,
    setup_icon_path,
    write_defines_iss,
)


class TestInstallerIdentity(unittest.TestCase):
    def test_stable_app_id(self):
        self.assertTrue(APP_ID_STABLE)
        self.assertRegex(
            INNO_APP_ID_GUID,
            r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$",
        )
        self.assertEqual(INNO_APP_ID, "{{" + INNO_APP_ID_GUID + "}}")
        # Never rotate casually: this exact GUID is the upgrade identity.
        self.assertEqual(INNO_APP_ID_GUID, "AC33C948-D619-47A0-8809-D99468EF9297")

    def test_installer_filename_from_app_version(self):
        self.assertEqual(
            installer_filename(APP_VERSION),
            f"NC-Code-Generator-Setup-{APP_VERSION}.exe",
        )
        self.assertEqual(
            installer_filename("0.1.4"),
            "NC-Code-Generator-Setup-0.1.4.exe",
        )
        self.assertNotEqual(
            installer_filename("0.1.3"),
            installer_filename(APP_VERSION),
        )

    def test_metadata_defines_from_app_info(self):
        defs = metadata_defines()
        self.assertEqual(defs["MyAppName"], APP_NAME)
        self.assertEqual(defs["MyAppVersion"], APP_VERSION)
        self.assertEqual(defs["MyAppVersionInfo"], WINDOWS_FILE_VERSION)
        self.assertEqual(defs["MyAppPublisher"], WINDOWS_COMPANY_NAME or APP_AUTHOR)
        self.assertEqual(defs["MyAppURL"], APP_WEBSITE_URL)
        self.assertEqual(defs["MyAppExeName"], EXE_FILENAME)
        self.assertEqual(defs["MyAppId"], INNO_APP_ID)
        self.assertEqual(defs["MyAppDescription"], APP_DESCRIPTION)
        self.assertEqual(defs["MyAppVersion"], APP_VERSION)

    def test_generated_defines_utf8_from_app_info(self):
        from app_info import APP_COPYRIGHT

        path = write_defines_iss()
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8-sig")
        self.assertIn(f'#define MyAppVersion "{APP_VERSION}"', text)
        self.assertIn(APP_COPYRIGHT, text)
        self.assertIn(APP_DESCRIPTION, text)
        assert_iss_has_no_hardcoded_app_version(read_iss_text())
        self.assertIn("MyAppDefinesInclude", read_iss_text())


class TestIssScript(unittest.TestCase):
    def setUp(self):
        self.iss = read_iss_text()
        self.path = iss_script_path()

    def test_iss_exists(self):
        self.assertTrue(self.path.is_file())

    def test_no_hardcoded_version_source(self):
        assert_iss_has_no_hardcoded_app_version(self.iss)
        self.assertNotRegex(self.iss, r'#\s*define\s+MyAppVersion\s+"')
        self.assertNotIn('#define MyAppVersion "0.1.4"', self.iss)
        self.assertNotIn('#define MyAppVersion "0.1.3"', self.iss)

    def test_architecture_x64(self):
        self.assertIn("ArchitecturesAllowed=x64compatible", self.iss)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", self.iss)

    def test_install_dir_program_files(self):
        self.assertIn(r"DefaultDirName={autopf}\{#MyAppName}", self.iss)
        self.assertEqual(DEFAULT_INSTALL_DIR_INNO, r"{autopf}\NC-Code Generator")
        self.assertNotIn(r"{localappdata}", self.iss.lower())
        self.assertNotIn("AppData", self.iss)

    def test_exe_and_icon(self):
        self.assertIn("MyAppExeName", self.iss)
        self.assertTrue(setup_icon_path().is_file())
        self.assertIn("app_icon.ico", self.iss)
        self.assertIn(APP_ICON_ICO_REL.replace("\\", "/").split("/")[-1], self.iss)
        self.assertIn(r"{app}\assets\app_icon.ico", self.iss)

    def test_output_basename_uses_define(self):
        self.assertIn(
            "OutputBaseFilename=NC-Code-Generator-Setup-{#MyAppVersion}",
            self.iss,
        )

    def test_desktop_shortcut_optional(self):
        self.assertIn('Name: "desktopicon"', self.iss)
        self.assertIn("Flags: unchecked", self.iss)
        self.assertIn("Tasks: desktopicon", self.iss)

    def test_start_menu_and_postinstall(self):
        self.assertIn(r"{autoprograms}\{#MyAppName}", self.iss)
        self.assertIn("skipifsilent", self.iss)
        self.assertIn("postinstall", self.iss)

    def test_admin_offline_no_python(self):
        self.assertIn("PrivilegesRequired=admin", self.iss)
        self.assertNotRegex(self.iss, r"(?im)^\s*Download")
        self.assertNotIn("pip install", self.iss.lower())
        self.assertNotIn("python.org", self.iss.lower())
        # No updater implementation section / executable hooks.
        self.assertNotIn("AutoUpdater", self.iss)
        self.assertNotIn("check_for_updates", self.iss.lower())

    def test_user_data_not_uninstalled(self):
        self.assertIn("never deleted", self.iss.lower())
        # Real UninstallDelete section would start a line with [UninstallDelete]
        self.assertNotRegex(self.iss, r"(?m)^\[UninstallDelete\]")

    def test_downgrade_guard_present(self):
        guard = (self.path.parent / "version_guard.iss").read_text(encoding="utf-8")
        self.assertIn("function CompareSemVer", guard)
        self.assertIn("function InitializeSetup", guard)
        self.assertIn(
            "Eine neuere Version des NC-Code Generators ist bereits installiert.",
            guard,
        )
        self.assertIn("GetInstalledDisplayVersion", guard)
        self.assertIn("Uninstall", guard)
        self.assertIn('#include "version_guard.iss"', self.iss)
        self.assertNotIn('#define MyAppVersion "', guard)

    def test_appid_injected_not_rotated_inline_guid_only(self):
        self.assertIn("AppId={#MyAppId}", self.iss)
        self.assertIn("APP_ID_STABLE", self.iss)


if __name__ == "__main__":
    unittest.main()
