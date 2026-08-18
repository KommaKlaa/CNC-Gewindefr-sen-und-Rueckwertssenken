"""RELEASE.1 – Release-Helfer ohne Nuitka-Vollcompile."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))

from app_info import APP_AUTHOR, APP_EMAIL, APP_NAME, APP_VERSION, APP_WEBSITE, EXE_FILENAME, WINDOWS_FILE_VERSION
from release_packaging import (
    ReleaseAborted,
    arch_from_pointer_and_machine,
    assert_clean_payload,
    assert_zip_top_level,
    build_manifest_payload,
    copy_dist,
    create_zip,
    python_architecture,
    release_folder_name,
    render_readme,
    render_release_info,
    require_dist,
    scan_forbidden,
    sha256_file,
    sha256sums_text,
    verify_sha256sums,
    windows_platform_tag,
    write_sha256sums,
    write_zip_sha256,
)


class TestReleaseNameAndArch(unittest.TestCase):
    def test_release_name_from_app_version(self):
        name = release_folder_name(APP_VERSION, "Windows_x64")
        self.assertEqual(name, f"NC-Code-Generator_{APP_VERSION}_Windows_x64")
        self.assertIn(APP_VERSION, name)
        self.assertNotIn("0.1.0", name)

    def test_release_name_rejects_free_version_strings(self):
        with self.assertRaises(ValueError):
            release_folder_name("0.1.0-beta", "Windows_x64")

    def test_architecture_helpers(self):
        self.assertEqual(arch_from_pointer_and_machine(64, "AMD64"), "x64")
        self.assertEqual(arch_from_pointer_and_machine(64, "x86_64"), "x64")
        self.assertEqual(windows_platform_tag("x64"), "Windows_x64")
        self.assertEqual(python_architecture(), "x64")
        self.assertEqual(
            release_folder_name(APP_VERSION, windows_platform_tag("x64")),
            f"NC-Code-Generator_{APP_VERSION}_Windows_x64",
        )


class TestSha256AndLayout(unittest.TestCase):
    def test_sha256_and_relative_sorted_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "z.bin").write_bytes(b"z")
            (root / "assets" / "app_icon.png").write_bytes(b"png")
            (root / "a.bin").write_bytes(b"a")
            text = sha256sums_text(root)
            lines = [ln for ln in text.splitlines() if ln]
            names = [ln.split("  ", 1)[1] for ln in lines]
            self.assertEqual(names, sorted(names, key=str.lower))
            self.assertIn("assets/app_icon.png", names)
            self.assertNotIn("SHA256SUMS.txt", names)
            expected_a = hashlib.sha256(b"a").hexdigest()
            self.assertTrue(any(ln.startswith(expected_a) and ln.endswith("a.bin") for ln in lines))
            write_sha256sums(root)
            verify_sha256sums(root)

    def test_zip_single_top_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / f"NC-Code-Generator_{APP_VERSION}_Windows_x64"
            folder.mkdir()
            (folder / "NC-Code-Generator.exe").write_bytes(b"fake")
            (folder / "README.txt").write_text("hi", encoding="utf-8")
            zip_path = Path(tmp) / f"NC-Code-Generator_{APP_VERSION}_Windows_x64.zip"
            create_zip(folder, zip_path, folder.name)
            assert_zip_top_level(zip_path, folder.name)
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
            self.assertTrue(all(n.startswith(folder.name + "/") for n in names))
            sidecar, digest = write_zip_sha256(zip_path)
            self.assertEqual(digest, sha256_file(zip_path))
            listed = sidecar.read_text(encoding="utf-8").strip()
            self.assertTrue(listed.startswith(digest))
            self.assertIn(zip_path.name, listed)

    def test_forbidden_source_and_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.dll").write_bytes(b"dll")
            self.assertEqual(scan_forbidden(root)["source"], [])
            (root / "bsf_blade.py").write_text("print(1)\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "x.txt").write_text("t", encoding="utf-8")
            (root / "sample.bgf.json").write_text("{}", encoding="utf-8")
            found = scan_forbidden(root)
            self.assertIn("bsf_blade.py", found["source"])
            self.assertTrue(any(x.startswith("tests/") for x in found["dev"]))
            self.assertIn("sample.bgf.json", found["user"])
            with self.assertRaises(ReleaseAborted):
                assert_clean_payload(root)

    def test_missing_dist_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "missing.dist"
            exe = dist / EXE_FILENAME
            with self.assertRaises(ReleaseAborted):
                require_dist(dist, exe)
            dist.mkdir()
            with self.assertRaises(ReleaseAborted):
                require_dist(dist, exe)

    def test_copy_dist_does_not_pick_individual_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "src"
            dest = Path(tmp) / "dst"
            dist.mkdir()
            (dist / "NC-Code-Generator.exe").write_bytes(b"exe")
            (dist / "lib.dll").write_bytes(b"dll")
            (dist / "nuitka-compilation-report.xml").write_text("<xml/>", encoding="utf-8")
            copy_dist(dist, dest)
            self.assertTrue((dest / "NC-Code-Generator.exe").is_file())
            self.assertTrue((dest / "lib.dll").is_file())
            self.assertFalse((dest / "nuitka-compilation-report.xml").exists())


class TestDocsAndManifest(unittest.TestCase):
    def test_readme_and_release_info_consistency(self):
        readme = render_readme(APP_VERSION)
        info = render_release_info(
            {
                "python_version": "3.11.9",
                "nuitka_version": "4.1.3",
                "architecture": "x64",
            }
        )
        self.assertIn(APP_NAME, readme)
        self.assertIn(APP_VERSION, readme)
        self.assertIn(EXE_FILENAME, readme)
        self.assertIn("zusammenbleiben", readme)
        self.assertIn("Werkzeug-Stirnfläche", readme)
        self.assertIn("8.550 mm", readme)
        self.assertIn("11.400 mm", readme)
        self.assertIn(APP_AUTHOR, info)
        self.assertIn(APP_WEBSITE, info)
        self.assertIn(APP_EMAIL, info)
        self.assertIn("TECHNICAL RELEASE PACKAGE", info)
        self.assertIn("HEULE BSF REAL TOOL VALIDATION:", info)
        self.assertIn("YES", info)
        self.assertNotIn("HEULE real tool validation completed", readme.lower())
        self.assertNotIn("HEULE real tool validation completed", info.lower())

    def test_manifest_fields(self):
        root = Path(__file__).resolve().parents[1]
        with mock.patch("release_packaging.detect_nuitka_version", return_value="4.1.3"):
            payload = build_manifest_payload(root, architecture="x64", console=False)
        self.assertEqual(payload["app_name"], APP_NAME)
        self.assertEqual(payload["app_version"], APP_VERSION)
        self.assertEqual(payload["windows_file_version"], WINDOWS_FILE_VERSION)
        self.assertEqual(payload["architecture"], "x64")
        self.assertEqual(payload["build_mode"], "standalone")
        self.assertIs(payload["console"], False)
        self.assertIs(payload["bsf_real_tool_validated"], True)
        self.assertTrue(payload["source_fingerprint"])
        self.assertIn("build_timestamp_utc", payload)
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
