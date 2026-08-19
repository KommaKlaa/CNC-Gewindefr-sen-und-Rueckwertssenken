"""INSTALLER.1 – Packager-Helfer, fail-closed Compiler, Payload-Pruefung."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))

from app_info import APP_VERSION, EXE_FILENAME
from installer_config import (
    INNO_SETUP_NOT_FOUND,
    InstallerAborted,
    find_iscc,
    installer_filename,
    installer_sha256_filename,
    require_iscc,
    validate_installer_payload,
    verify_installer_sha256,
    write_installer_sha256,
)
from release_packaging import ReleaseAborted, project_root


class TestInstallerSha256Helper(unittest.TestCase):
    def test_write_and_verify_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / installer_filename("9.9.9")
            path.write_bytes(b"setup-bytes")
            sidecar, digest = write_installer_sha256(path)
            self.assertEqual(digest, hashlib.sha256(b"setup-bytes").hexdigest())
            self.assertEqual(sidecar.name, installer_sha256_filename("9.9.9"))
            self.assertEqual(verify_installer_sha256(path, sidecar), digest)
            listed = sidecar.read_text(encoding="utf-8")
            self.assertTrue(listed.startswith(digest))
            self.assertIn(path.name, listed)


class TestCompilerDiscovery(unittest.TestCase):
    def test_env_invalid_fail_closed(self):
        with mock.patch.dict(
            os.environ,
            {"INNO_SETUP_COMPILER": r"C:\missing\ISCC.exe"},
            clear=False,
        ):
            self.assertIsNone(find_iscc())
            with self.assertRaises(InstallerAborted) as ctx:
                require_iscc()
            self.assertEqual(str(ctx.exception), INNO_SETUP_NOT_FOUND)

    def test_env_points_to_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "ISCC.exe"
            fake.write_bytes(b"fake")
            with mock.patch.dict(
                os.environ,
                {"INNO_SETUP_COMPILER": str(fake)},
                clear=False,
            ):
                found = find_iscc()
            self.assertEqual(found, fake.resolve())


class TestPayloadValidation(unittest.TestCase):
    def test_rejects_source_files(self):
        root = project_root()
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp)
            (payload / EXE_FILENAME).write_bytes(b"MZ")
            (payload / "runtime.dll").write_bytes(b"dll")
            (payload / "assets").mkdir()
            (payload / "assets" / "app_icon.ico").write_bytes(b"ico")
            (payload / "secret.py").write_text("print(1)\n", encoding="utf-8")
            with self.assertRaises(ReleaseAborted):
                validate_installer_payload(root, payload)

    def test_version_drift_detection(self):
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
                return_value={"FileVersionNumeric": "9.9.9.0"},
            ), mock.patch(
                "installer_config.load_build_manifest",
                return_value={
                    "app_version": "9.9.9",
                    "windows_file_version": "9.9.9.0",
                    "source_fingerprint": "deadbeef",
                },
            ):
                with self.assertRaises(InstallerAborted) as ctx:
                    validate_installer_payload(root, payload)
            self.assertIn("Version-Drift", str(ctx.exception))
            self.assertIn(APP_VERSION, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
