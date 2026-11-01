"""UI tests for opening and creating modules."""

import unittest

from gpredict_ui import Gpredict, click, click_until, find, is_focused, \
    is_selected, is_sensitive, text_of, type_text, wait_for


class OpenModuleTest(unittest.TestCase):

    def open_module(self, gp, name):
        gp.menu("File", "Open module")
        dialog = gp.dialog("Select a module")
        cell = wait_for(lambda: find(dialog, "table cell", name),
                        "module '%s' in the list" % name)
        click_until(cell, lambda: is_selected(cell),
                    "module '%s' to be selected" % name)
        click(find(dialog, "button", "OK"))
        gp.wait_dialog_closed("Select a module")

    def test_open_module(self):
        with Gpredict(modules=["Amateur", "Weather"]) as gp:
            self.assertEqual(gp.module_tabs(), ["Amateur"])

            self.open_module(gp, "Weather")

            wait_for(lambda: len(gp.module_tabs()) == 2, "a second tab")
            self.assertEqual(gp.module_tabs(), ["Amateur", "Weather"])
            self.assertEqual(gp.main_window().get_name(), "Gpredict: Weather")

    def test_open_module_twice(self):
        with Gpredict(modules=["Amateur", "Weather"]) as gp:
            self.open_module(gp, "Weather")
            wait_for(lambda: len(gp.module_tabs()) == 2, "a second tab")

            # the already open module is brought to the front
            self.open_module(gp, "Amateur")

            wait_for(lambda: gp.main_window().get_name() ==
                     "Gpredict: Amateur", "Amateur to be selected")
            self.assertEqual(gp.module_tabs(), ["Amateur", "Weather"])

    def test_restore_skips_duplicates(self):
        with Gpredict(modules=["Amateur", "Weather"],
                      open_modules="Amateur;Weather;Amateur") as gp:
            self.assertEqual(gp.module_tabs(), ["Amateur", "Weather"])


class NewModuleTest(unittest.TestCase):

    def test_module_name_entry(self):
        with Gpredict() as gp:
            gp.menu("File", "New module")
            dialog = gp.dialog("Create new module")
            entry = find(dialog, "text")
            ok = find(dialog, "button", "OK")
            self.assertFalse(is_sensitive(ok))

            # characters that are not allowed in a file name are dropped
            click_until(entry, lambda: is_focused(entry),
                        "the module name entry to get the focus")
            type_text("ISS pass/2")

            wait_for(lambda: text_of(entry) == "ISSpass2",
                     "the module name to be filtered")
            self.assertTrue(is_sensitive(ok))

            click(find(dialog, "button", "Cancel"))
            gp.wait_dialog_closed("Create new module")
            self.assertEqual(gp.module_tabs(), ["Amateur"])


if __name__ == "__main__":
    unittest.main()
