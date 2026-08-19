"""INSTALLER.2 – SemVer, SHA256SUMS, Orchestrierung, stale Payload."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))

from app_info import APP_VERSION
from create_windows_release import _nuitka_once, write_windows_release_manifest
from installer_config import (
    CODE_SIGNING,
    APP_ID_STABLE,
    INNO_APP_ID_GUID,
    InstallerAborted,
    compare_semver,
    downgrade_should_block,
    parse_semver,
    verify_asset_sha256sums,
    windows_release_asset_names,
    write_asset_sha256sums,
    write_named_sha256,
    verify_named_sha256,
)
from release_packaging import project_root


class TestNumericSemVer(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(compare_semver("0.1.3", "0.1.4"), -1)
        self.assertEqual(compare_semver("0.1.9", "0.1.10"), -1)
        self.assertEqual(compare_semver("0.2.0", "0.1.99"), 1)
        self.assertEqual(compare_semver("1.0.0", "0.99.99"), 1)
        self.assertEqual(compare_semver("0.1.4", "0.1.4"), 0)
        self.assertEqual(parse_semver("0.1.10"), (0, 1, 10))

    def test_not_lexicographic(self):
        self.assertLess(parse_semver("0.1.9"), parse_semver("0.1.10"))
        self.assertTrue(downgrade_should_block("0.1.5", "0.1.4"))
        self.assertFalse(downgrade_should_block("0.1.4", "0.1.4"))
        self.assertFalse(downgrade_should_block("0.1.3", "0.1.4"))

    def test_rejects_free_strings(self):
        with self.assertRaises(ValueError):
            parse_semver("0.1.0-beta")
        with self.assertRaises(ValueError):
            compare_semver("1.0", "1.0.0")


class TestReleaseAssetNamesAndSums(unittest.TestCase):
    def test_names_from_app_version(self):
        names = windows_release_asset_names(APP_VERSION)
        self.assertEqual(names["folder"], f"NC-Code-Generator_{APP_VERSION}_Windows_x64")
        self.assertEqual(names["setup"], f"NC-Code-Generator-Setup-{APP_VERSION}.exe")
        self.assertNotIn("0.1.4", names["setup"])
        future = windows_release_asset_names("0.1.4")
        self.assertEqual(future["setup"], "NC-Code-Generator-Setup-0.1.4.exe")
        self.assertEqual(future["zip"], "NC-Code-Generator_0.1.4_Windows_x64.zip")

    def test_sidecar_and_sha256sums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "NC-Code-Generator_9.9.9_Windows_x64.zip"
            setup = root / "NC-Code-Generator-Setup-9.9.9.exe"
            zip_path.write_bytes(b"zip-bytes")
            setup.write_bytes(b"setup-bytes")
            zside, zdig = write_named_sha256(zip_path)
            sside, sdig = write_named_sha256(setup)
            self.assertEqual(verify_named_sha256(zip_path, zside), zdig)
            self.assertEqual(verify_named_sha256(setup, sside), sdig)
            sums = root / "SHA256SUMS.txt"
            write_asset_sha256sums([zip_path, setup], sums)
            verify_asset_sha256sums([zip_path, setup], sums)
            text = sums.read_text(encoding="utf-8")
            self.assertIn(zip_path.name, text)
            self.assertIn(setup.name, text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("\\", text.split("  ", 1)[-1])
            lines = [ln for ln in text.splitlines() if ln]
            names = [ln.split("  ", 1)[1] for ln in lines]
            self.assertEqual(names, sorted(names, key=str.lower))

    def test_manifest_rejects_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "release_manifest.json"
            with self.assertRaises(InstallerAborted):
                write_windows_release_manifest(
                    dest,
                    {"source_head": "abc", "note": r"E:\Jens\secret"},
                )
            write_windows_release_manifest(
                dest,
                {
                    "app_version": APP_VERSION,
                    "windows_version": "0.1.3.0",
                    "code_signing": CODE_SIGNING,
                    "nuitka_build_count": 1,
                },
            )
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(data["code_signing"], "NOT_CONFIGURED")
            blob = dest.read_text(encoding="utf-8")
            self.assertNotIn("E:\\Jens", blob)
            self.assertNotIn("C:\\Users", blob)


class TestOrchestrationGuards(unittest.TestCase):
    def test_stable_app_id_unchanged(self):
        self.assertTrue(APP_ID_STABLE)
        self.assertEqual(INNO_APP_ID_GUID, "AC33C948-D619-47A0-8809-D99468EF9297")

    def test_nuitka_once_fail_closed(self):
        counter = [0]
        with mock.patch("create_windows_release._run_nuitka"):
            _nuitka_once(Path("."), counter)
            self.assertEqual(counter[0], 1)
            with self.assertRaises(InstallerAborted) as ctx:
                _nuitka_once(Path("."), counter)
            self.assertIn("NUITKA_BUILD_COUNT", str(ctx.exception))

    def test_overwrite_blocked_for_existing_0_1_3(self):
        from create_windows_release import run_windows_release

        with self.assertRaises((InstallerAborted, SystemExit)) as ctx:
            run_windows_release(
                ["--skip-tests", "--skip-smoke", "--skip-install-smoke", "--allow-dirty"]
            )
        self.assertIn("OVERWRITE_BLOCKED", str(ctx.exception))

    def test_installer_builder_does_not_call_nuitka(self):
        root = project_root()
        text = (root / "build_tools" / "create_installer.py").read_text(encoding="utf-8")
        self.assertNotIn("nuitka_standalone", text)
        self.assertNotIn("_run_nuitka", text)

    def test_code_signing_not_configured(self):
        self.assertEqual(CODE_SIGNING, "NOT_CONFIGURED")


class TestStalePayloadFingerprint(unittest.TestCase):
    def test_fingerprint_mismatch_blocked(self):
        from installer_config import validate_installer_payload
        from app_info import EXE_FILENAME

        root = project_root()
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp)
            (payload / EXE_FILENAME).write_bytes(b"MZ fake")
            (payload / "runtime.dll").write_bytes(b"dll")
            (payload / "assets").mkdir()
            (payload / "assets" / "app_icon.ico").write_bytes(b"ico")
            with mock.patch(
                "installer_config.pe_architecture",
                return_value="x64",
            ), mock.patch(
                "installer_config.assert_exe_matches_app_info",
                return_value={"FileVersionNumeric": "0.1.3.0"},
            ), mock.patch(
                "installer_config.load_build_manifest",
                return_value={
                    "app_version": APP_VERSION,
                    "windows_file_version": "0.1.3.0",
                    "source_fingerprint": "not-the-real-fingerprint",
                },
            ):
                with self.assertRaises(InstallerAborted) as ctx:
                    validate_installer_payload(root, payload)
            self.assertIn("Fingerprint", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
