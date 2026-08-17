"""PHASE APP.ICON.1 – Resource-Pfade und fail-safe Fenster-Icon."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import app_paths
import bsf_generator_verbessert_v3 as gen
from app_paths import APP_ICON_ICO_REL, APP_ICON_PNG_REL, apply_window_icon, resource_path


class TestResourcePath(unittest.TestCase):
    def test_resolves_assets_under_project_root(self):
        ico = resource_path(APP_ICON_ICO_REL)
        png = resource_path(APP_ICON_PNG_REL)
        root = Path(app_paths.__file__).resolve().parent
        self.assertEqual(ico, (root / APP_ICON_ICO_REL).resolve())
        self.assertEqual(png, (root / APP_ICON_PNG_REL).resolve())

    def test_icon_assets_exist(self):
        self.assertTrue(resource_path(APP_ICON_ICO_REL).is_file(), "assets/app_icon.ico fehlt")
        self.assertTrue(resource_path(APP_ICON_PNG_REL).is_file(), "assets/app_icon.png fehlt")

    def test_legacy_meipass_when_present(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_base = Path(tmp)
            (fake_base / "assets").mkdir()
            marker = fake_base / "assets" / "app_icon.ico"
            marker.write_bytes(b"ico")
            with mock.patch.object(sys, "frozen", True, create=True):
                with mock.patch.object(sys, "_MEIPASS", str(fake_base), create=True):
                    resolved = resource_path("assets/app_icon.ico")
        self.assertEqual(resolved, marker.resolve())

    def test_nuitka_standalone_uses_exe_directory(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "assets").mkdir()
            marker = dist / "assets" / "app_icon.png"
            marker.write_bytes(b"png")
            fake_exe = dist / "NC-Code-Generator.exe"
            with mock.patch.object(sys, "frozen", True, create=True):
                with mock.patch.object(sys, "_MEIPASS", None, create=True):
                    with mock.patch.object(sys, "executable", str(fake_exe)):
                        resolved = resource_path("assets/app_icon.png")
        self.assertEqual(resolved, marker.resolve())

    def test_resource_path_ignores_cwd(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                png = resource_path(APP_ICON_PNG_REL)
                self.assertTrue(png.is_file())
                self.assertEqual(png.name, "app_icon.png")
            finally:
                os.chdir(old)


class TestApplyWindowIcon(unittest.TestCase):
    def test_missing_icon_returns_false_without_exception(self):
        window = mock.Mock()
        self.assertFalse(
            apply_window_icon(window, ico_relative="assets/does_not_exist.ico")
        )
        window.iconbitmap.assert_not_called()

    def test_present_icon_calls_iconbitmap(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            self.assertTrue(apply_window_icon(root))
        finally:
            root.destroy()

    def test_tcl_error_is_swallowed(self):
        import tkinter as tk

        window = mock.Mock()
        window.iconbitmap.side_effect = tk.TclError("boom")
        self.assertFalse(apply_window_icon(window, ico_relative=APP_ICON_ICO_REL))


class TestGuiStartsWithoutIcon(unittest.TestCase):
    def test_main_window_starts_when_icon_missing(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        with mock.patch("bsf_generator_verbessert_v3.apply_window_icon", return_value=False):
            app = gen.BSFGeneratorGUI(root)
        self.assertTrue(app.root.winfo_exists())
        root.destroy()

    def test_preview_window_starts_when_icon_missing(self):
        import tkinter as tk

        from preview.bgf_preview_model import PreviewSnapshot
        from preview.bgf_preview_window import BGFPreviewWindow

        root = tk.Tk()
        root.withdraw()

        def provider():
            return PreviewSnapshot(
                mode_label="Test",
                thread_size="M10",
                article_no="123",
                tool_radius=1.0,
                tool_number=8,
                program_name="T",
                approach_clearance=1.0,
                safe_z=100.0,
                end_safe_z=200.0,
            )

        with mock.patch("preview.bgf_preview_window.apply_window_icon", return_value=False):
            win = BGFPreviewWindow(root, snapshot_provider=provider)
        self.assertTrue(win.win.winfo_exists())
        win.win.destroy()
        root.destroy()


if __name__ == "__main__":
    unittest.main()
