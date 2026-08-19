"""Tests fuer Sicherheits- und Nutzungshinweis (PHASE SAFETY.NOTICE.1)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tkinter as tk
from tkinter import ttk

from app_info import APP_VERSION

import safety_notice as sn


class TestSafetyNoticeText(unittest.TestCase):
    def test_nc_review_required_wording(self):
        text = sn.SAFETY_NOTICE_TEXT.lower()
        self.assertIn("nicht ungeprüft", text)
        self.assertIn("zu prüfen", text)

    def test_own_risk_wording(self):
        self.assertIn("eigenverantwortlich", sn.SAFETY_NOTICE_TEXT)

    def test_brands_mentioned(self):
        self.assertIn("HEULE", sn.SAFETY_NOTICE_TEXT)
        self.assertIn("CERATIZIT", sn.SAFETY_NOTICE_TEXT)

    def test_trademark_wording(self):
        self.assertIn(
            "Marken bzw. eingetragene Marken ihrer jeweiligen Rechteinhaber",
            sn.SAFETY_NOTICE_TEXT,
        )

    def test_no_manufacturer_approval_claim(self):
        text = sn.SAFETY_NOTICE_TEXT.lower()
        self.assertIn("kein produkt", text)
        self.assertIn("keine freigabe", text)
        for forbidden in (
            "approved by heule",
            "approved by ceratizit",
            "offiziell kompatibel",
            "jegliche haftung ist ausgeschlossen",
        ):
            self.assertNotIn(forbidden, text)

    def test_simulation_dry_run_recommended(self):
        text = sn.SAFETY_NOTICE_TEXT.lower()
        self.assertIn("simulation", text)
        self.assertIn("trockenlauf", text)


class TestSafetyNoticePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_start_not_accepted(self):
        self.assertFalse(sn.is_safety_notice_accepted("0.1.1", path=self.settings_path))

    def test_acceptance_stored_per_version(self):
        sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"accepted_safety_notice_version": "0.1.1"})
        self.assertTrue(sn.is_safety_notice_accepted("0.1.1", path=self.settings_path))
        self.assertFalse(sn.is_safety_notice_accepted("0.1.2", path=self.settings_path))

    def test_new_version_requires_new_acceptance(self):
        sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        self.assertFalse(sn.is_safety_notice_accepted("0.1.2", path=self.settings_path))

    def test_previous_release_acceptance_does_not_apply_to_current(self):
        sn.record_safety_notice_acceptance("0.1.2", path=self.settings_path)
        self.assertTrue(sn.is_safety_notice_accepted("0.1.2", path=self.settings_path))
        self.assertFalse(sn.is_safety_notice_accepted(APP_VERSION, path=self.settings_path))

    def test_v013_acceptance_does_not_cover_v014(self):
        sn.record_safety_notice_acceptance("0.1.3", path=self.settings_path)
        self.assertTrue(sn.is_safety_notice_accepted("0.1.3", path=self.settings_path))
        self.assertFalse(sn.is_safety_notice_accepted("0.1.4", path=self.settings_path))
        sn.record_safety_notice_acceptance("0.1.4", path=self.settings_path)
        self.assertTrue(sn.is_safety_notice_accepted("0.1.4", path=self.settings_path))

    def test_persistence_failure_fail_open_after_acceptance(self):
        with mock.patch.object(sn, "save_settings", return_value=False):
            ok = sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        self.assertFalse(ok)
        self.assertFalse(sn.is_safety_notice_accepted("0.1.1", path=self.settings_path))

    def test_no_personal_data_stored(self):
        sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(set(data.keys()), {sn.SETTINGS_KEY})


class TestSafetyNoticeStartupLogic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tmp.name) / "settings.json"
        self._prev_skip = os.environ.get(sn.ENV_SKIP)
        os.environ.pop(sn.ENV_SKIP, None)
        os.environ[sn.ENV_SETTINGS_PATH] = str(self.settings_path)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop(sn.ENV_SETTINGS_PATH, None)
        if self._prev_skip is None:
            os.environ.pop(sn.ENV_SKIP, None)
        else:
            os.environ[sn.ENV_SKIP] = self._prev_skip

    def test_accepted_same_version_skips_dialog(self):
        sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        with mock.patch.object(sn, "_should_skip_startup_notice", return_value=False):
            with mock.patch.object(sn, "show_startup_safety_notice") as show:
                root = tk.Tk()
                root.withdraw()
                try:
                    self.assertTrue(
                        sn.ensure_startup_safety_notice(
                            root,
                            app_version="0.1.1",
                            settings_path=self.settings_path,
                        )
                    )
                finally:
                    root.destroy()
        show.assert_not_called()

    def test_new_version_shows_dialog(self):
        sn.record_safety_notice_acceptance("0.1.1", path=self.settings_path)
        with mock.patch.object(sn, "_should_skip_startup_notice", return_value=False):
            with mock.patch.object(sn, "show_startup_safety_notice", return_value=True) as show:
                root = tk.Tk()
                root.withdraw()
                try:
                    self.assertTrue(
                        sn.ensure_startup_safety_notice(
                            root,
                            app_version="0.1.2",
                            settings_path=self.settings_path,
                        )
                    )
                finally:
                    root.destroy()
        show.assert_called_once()

    def test_decline_returns_false(self):
        with mock.patch.object(sn, "_should_skip_startup_notice", return_value=False):
            with mock.patch.object(sn, "show_startup_safety_notice", return_value=False):
                root = tk.Tk()
                root.withdraw()
                try:
                    self.assertFalse(
                        sn.ensure_startup_safety_notice(
                            root,
                            app_version="0.1.1",
                            settings_path=self.settings_path,
                        )
                    )
                finally:
                    root.destroy()


class TestSafetyNoticeDialog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tmp.name) / "settings.json"
        self._prev_skip = os.environ.get(sn.ENV_SKIP)
        os.environ.pop(sn.ENV_SKIP, None)

    def tearDown(self):
        self.tmp.cleanup()
        if self._prev_skip is None:
            os.environ.pop(sn.ENV_SKIP, None)
        else:
            os.environ[sn.ENV_SKIP] = self._prev_skip

    def _collect_button_texts(self, widget) -> list[str]:
        texts: list[str] = []
        if isinstance(widget, (ttk.Button, tk.Button)):
            texts.append(str(widget.cget("text")))
        for child in widget.winfo_children():
            texts.extend(self._collect_button_texts(child))
        return texts

    def test_startup_dialog_has_required_buttons(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(
            root,
            mode="startup",
            app_version="9.9.9-test",
            settings_path=self.settings_path,
        )
        dialog._build()
        try:
            win = dialog.win
            self.assertIsNotNone(win)
            assert win is not None
            self.assertEqual(win.title(), sn.SAFETY_NOTICE_TITLE)
            buttons = self._collect_button_texts(win)
            self.assertIn("Verstanden und akzeptiert", buttons)
            self.assertIn("Programm beenden", buttons)
            self.assertNotIn("Später", buttons)
            self.assertNotIn("Überspringen", buttons)
        finally:
            if dialog.win is not None and dialog.win.winfo_exists():
                dialog.win.destroy()
            root.destroy()

    def test_accept_records_version(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(
            root,
            mode="startup",
            app_version="9.9.9-test",
            settings_path=self.settings_path,
        )
        dialog._build()
        dialog._on_accept()
        self.assertTrue(dialog.accepted)
        self.assertTrue(sn.is_safety_notice_accepted("9.9.9-test", path=self.settings_path))
        root.destroy()

    def test_close_does_not_record_acceptance(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(
            root,
            mode="startup",
            app_version="9.9.9-test",
            settings_path=self.settings_path,
        )
        dialog._build()
        dialog._on_exit()
        self.assertFalse(dialog.accepted)
        self.assertFalse(sn.is_safety_notice_accepted("9.9.9-test", path=self.settings_path))
        root.destroy()

    def test_escape_binding_exists_and_is_not_accept(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(
            root,
            mode="startup",
            app_version="9.9.9-test",
            settings_path=self.settings_path,
        )
        dialog._build()
        try:
            assert dialog.win is not None
            self.assertTrue(dialog.win.bind("<Escape>"))
            dialog.win.event_generate("<Escape>")
            root.update()
            self.assertFalse(dialog.accepted)
            self.assertFalse(sn.is_safety_notice_accepted("9.9.9-test", path=self.settings_path))
        finally:
            if dialog.win is not None and dialog.win.winfo_exists():
                dialog.win.destroy()
            root.destroy()

    def test_accept_continues_even_if_save_fails(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(
            root,
            mode="startup",
            app_version="9.9.9-test",
            settings_path=self.settings_path,
        )
        dialog._build()
        with mock.patch.object(sn, "record_safety_notice_acceptance", return_value=False):
            dialog._on_accept()
        self.assertTrue(dialog.accepted)
        root.destroy()

    def test_help_dialog_has_close_only(self):
        root = tk.Tk()
        root.withdraw()
        dialog = sn._SafetyNoticeDialog(root, mode="help")
        dialog._build()
        try:
            win = dialog.win
            assert win is not None
            buttons = self._collect_button_texts(win)
            self.assertIn("Schließen", buttons)
            self.assertNotIn("Verstanden und akzeptiert", buttons)
        finally:
            if dialog.win is not None and dialog.win.winfo_exists():
                dialog.win.destroy()
            root.destroy()


class TestSafetyNoticeMenuIntegration(unittest.TestCase):
    def test_help_menu_contains_safety_entry(self):
        import bsf_generator_verbessert_v3 as gen

        root = tk.Tk()
        root.withdraw()
        try:
            app = gen.BSFGeneratorGUI(root)
            menu = app.root.nametowidget(app.root.cget("menu"))
            help_index = menu.index("Hilfe")
            help_menu = menu.nametowidget(menu.entrycget(help_index, "menu"))
            labels = []
            end = help_menu.index("end")
            if end is not None:
                for i in range(end + 1):
                    labels.append(help_menu.entrycget(i, "label"))
            self.assertIn("Sicherheits- und Nutzungshinweis", labels)
        finally:
            root.destroy()


class TestAboutTrademarkNotice(unittest.TestCase):
    def test_about_window_contains_trademark_notice(self):
        from ui.about import open_about_window

        root = tk.Tk()
        root.withdraw()
        try:
            win = open_about_window(root)
            texts: list[str] = []

            def collect(widget) -> None:
                try:
                    value = widget.cget("text")
                    if value:
                        texts.append(str(value))
                except tk.TclError:
                    pass
                for child in widget.winfo_children():
                    collect(child)

            collect(win)
            blob = "\n".join(texts)
            self.assertIn("HEULE", blob)
            self.assertIn("CERATIZIT", blob)
            self.assertIn("Keine Verbindung oder Herstellerfreigabe", blob)
            win.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
