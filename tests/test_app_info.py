"""Zentrale App-Metadaten, Info-Fenster, Nuitka-Pfade (PACKAGING.NUITKA.1)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import tkinter as tk
from tkinter import ttk

from app_info import (
    APP_AUTHOR,
    APP_COPYRIGHT,
    APP_DESCRIPTION,
    APP_EMAIL,
    APP_MAILTO,
    APP_NAME,
    APP_VERSION,
    APP_WEBSITE,
    APP_WEBSITE_URL,
    EXE_FILENAME,
    WINDOWS_COMPANY_NAME,
    WINDOWS_FILE_VERSION,
    WINDOWS_PRODUCT_VERSION,
    derive_windows_version,
)
from ui.about import _safe_open, open_about_window


class TestAppInfo(unittest.TestCase):
    def test_canonical_product_name(self):
        self.assertEqual(APP_NAME, "NC-Code Generator")
        self.assertEqual(APP_VERSION, "0.1.4")
        self.assertEqual(APP_AUTHOR, "Jens Behm")
        self.assertEqual(APP_WEBSITE, "behm-it.de")
        self.assertEqual(APP_WEBSITE_URL, "https://behm-it.de")
        self.assertEqual(APP_EMAIL, "info@behm-it.de")
        self.assertEqual(APP_MAILTO, "mailto:info@behm-it.de")
        self.assertEqual(APP_COPYRIGHT, "© 2026 Jens Behm")
        self.assertEqual(
            APP_DESCRIPTION,
            "NC-Code-Erstellung für HEULE BSF und CERATIZIT BGF",
        )
        self.assertEqual(WINDOWS_COMPANY_NAME, "Jens Behm")
        self.assertEqual(EXE_FILENAME, "NC-Code-Generator.exe")
        from app_info import BSF_REAL_TOOL_VALIDATED

        self.assertIs(BSF_REAL_TOOL_VALIDATED, True)

    def test_windows_version_from_semver(self):
        self.assertEqual(derive_windows_version("0.1.0"), "0.1.0.0")
        self.assertEqual(WINDOWS_FILE_VERSION, "0.1.4.0")
        self.assertEqual(WINDOWS_PRODUCT_VERSION, "0.1.4.0")
        self.assertEqual(WINDOWS_FILE_VERSION, WINDOWS_PRODUCT_VERSION)

    def test_windows_version_rejects_free_strings(self):
        with self.assertRaises(ValueError):
            derive_windows_version("0.1.0-beta")
        with self.assertRaises(ValueError):
            derive_windows_version("1.0")
        with self.assertRaises(ValueError):
            derive_windows_version("")


class TestAboutWindow(unittest.TestCase):
    def test_readonly_content_and_title(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            win = open_about_window(root)
            self.assertEqual(win.title(), f"Info – {APP_NAME}")
            texts = []
            for child in win.winfo_children():
                texts.extend(self._collect_texts(child))
            blob = "\n".join(texts)
            self.assertIn(APP_NAME, blob)
            self.assertIn(f"Version {APP_VERSION}", blob)
            self.assertIn(APP_AUTHOR, blob)
            self.assertIn(APP_WEBSITE, blob)
            self.assertIn(APP_EMAIL, blob)
            self.assertIn(APP_COPYRIGHT, blob)
            self.assertIn("HEULE", blob)
            self.assertIn("CERATIZIT", blob)
            self.assertIn("Keine Verbindung oder Herstellerfreigabe", blob)
            self.assertFalse(self._has_entry(win))
            win.destroy()
        finally:
            root.destroy()

    def test_website_and_mail_links_fail_safe(self):
        with mock.patch("ui.about.webbrowser.open", side_effect=OSError("no browser")):
            _safe_open(APP_WEBSITE_URL)
            _safe_open(APP_MAILTO)

    def test_links_use_correct_urls(self):
        opened = []

        def capture(url):
            opened.append(url)
            return True

        with mock.patch("ui.about.webbrowser.open", side_effect=capture):
            _safe_open(APP_WEBSITE_URL)
            _safe_open(APP_MAILTO)
        self.assertEqual(opened, [APP_WEBSITE_URL, APP_MAILTO])

    def test_about_does_not_change_nc(self):
        import tkinter as tk

        import bsf_generator_verbessert_v3 as gen
        from ui import MODE_BGF

        root = tk.Tk()
        root.withdraw()
        try:
            app = gen.BSFGeneratorGUI(root)
            app.mode_var.set(MODE_BGF)
            app.on_mode_change(None)
            app.bgf_size_var.set("M10")
            app.load_bgf_values()
            app.position_mode_var.set("Einzelposition")
            app.on_position_mode_change(None)
            for key, val in (
                ("single_x", "0"),
                ("single_y", "0"),
                ("single_surface_z", "0"),
                ("approach_clearance", "5"),
                ("bgf_thread_depth", "20"),
                ("bgf_core_hole_depth", ""),
            ):
                app.entries[key].delete(0, tk.END)
                app.entries[key].insert(0, val)
            app.generate_bgf_code()
            before = app.output_text.get("1.0", tk.END)
            app.open_about_window()
            after_open = app.output_text.get("1.0", tk.END)
            for child in list(app.root.winfo_children()):
                if isinstance(child, tk.Toplevel) and child.title().startswith("Info"):
                    child.destroy()
            after_close = app.output_text.get("1.0", tk.END)
            self.assertEqual(before, after_open)
            self.assertEqual(before, after_close)
            self.assertIn("Z-19.8390", before)
        finally:
            root.destroy()

    def test_help_menu_exists(self):
        import tkinter as tk

        import bsf_generator_verbessert_v3 as gen

        root = tk.Tk()
        root.withdraw()
        try:
            app = gen.BSFGeneratorGUI(root)
            menu = app.root.nametowidget(app.root.cget("menu"))
            labels = []
            end = menu.index("end")
            if end is not None:
                for i in range(end + 1):
                    try:
                        if menu.type(i) in ("cascade", "command"):
                            labels.append(menu.entrycget(i, "label"))
                    except tk.TclError:
                        continue
            self.assertIn("Hilfe", labels)
        finally:
            root.destroy()

    def _collect_texts(self, widget) -> list[str]:
        texts = []
        try:
            value = widget.cget("text")
            if value:
                texts.append(str(value))
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            texts.extend(self._collect_texts(child))
        return texts

    def _has_entry(self, widget) -> bool:
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            return True
        return any(self._has_entry(child) for child in widget.winfo_children())


class TestNuitkaBuildCommand(unittest.TestCase):
    def test_standalone_options_from_app_info(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_tools"))
        from nuitka_standalone import dist_exe_path, nuitka_command, project_root

        cmd = " ".join(nuitka_command(console_mode="disable"))
        self.assertIn("--mode=standalone", cmd)
        self.assertNotIn("--mode=onefile", cmd)
        self.assertIn("--windows-console-mode=disable", cmd)
        self.assertIn("--windows-icon-from-ico=assets/app_icon.ico", cmd)
        self.assertIn(f"--output-filename={EXE_FILENAME}", cmd)
        self.assertIn(f'--product-name={APP_NAME}', cmd)
        self.assertIn(f"--product-version={WINDOWS_PRODUCT_VERSION}", cmd)
        self.assertIn(f"--file-version={WINDOWS_FILE_VERSION}", cmd)
        self.assertIn(APP_DESCRIPTION, cmd)
        self.assertIn(APP_COPYRIGHT, cmd)
        self.assertIn(f"--company-name={WINDOWS_COMPANY_NAME}", cmd)
        self.assertIn("--include-data-dir=assets=assets", cmd)
        self.assertNotIn("E:\\Jens", cmd)
        self.assertNotIn("--include-data-files=", cmd)
        exe = dist_exe_path(project_root())
        self.assertEqual(exe.name, EXE_FILENAME)
        self.assertTrue(str(exe).endswith(os.path.join("build", "NC-Code-Generator.dist", EXE_FILENAME)))


if __name__ == "__main__":
    unittest.main()
