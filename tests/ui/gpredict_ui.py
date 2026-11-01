"""
Helpers for driving gpredict through the accessibility interface (AT-SPI).

Widgets are looked up in the accessibility tree by role and name. Clicks and
key presses are sent as real input events, because activating a widget
through AT-SPI blocks while gpredict runs a modal dialog.

gpredict runs with a temporary configuration directory, filled with the
default configuration from the source tree, so the tests never touch or
depend on the user's configuration. They should run on a private X display, see
run-ui-tests.sh.
"""

import os
import shutil
import subprocess
import tempfile
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

TIMEOUT = 10
SRCDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def wait_for(func, what, timeout=TIMEOUT):
    """Call func until it returns a true value and return that value."""
    end = time.monotonic() + timeout
    while True:
        result = func()
        if result:
            return result
        if time.monotonic() > end:
            raise AssertionError("Timed out waiting for " + what)
        time.sleep(0.1)


def find_all(node, role, name=None):
    """Return all nodes below node with the given role and name."""
    found = []
    if node.get_role_name() == role and name in (None, node.get_name()):
        found.append(node)
    for i in range(node.get_child_count()):
        child = node.get_child_at_index(i)
        if child is not None:
            found.extend(find_all(child, role, name))
    return found


def find(node, role, name=None):
    """Return the first node below node with the given role and name."""
    found = find_all(node, role, name)
    return found[0] if found else None


def click(node, button="b1c"):
    """Click the centre of node. Use button="b1d" for a double click."""
    ext = node.get_extents(Atspi.CoordType.SCREEN)
    Atspi.generate_mouse_event(ext.x + ext.width // 2,
                               ext.y + ext.height // 2, button)


def click_until(node, func, what, attempts=5):
    """
    Click node until func returns a true value and return that value.

    A click shortly after a window appears can get lost, so the click is
    repeated if it has no effect.
    """
    for _ in range(attempts):
        click(node)
        try:
            return wait_for(func, what, timeout=1)
        except AssertionError:
            pass
    raise AssertionError("Timed out waiting for " + what)


def type_text(text):
    """Type text into the widget that has the keyboard focus."""
    Atspi.generate_keyboard_event(0, text, Atspi.KeySynthType.STRING)


def text_of(node):
    """Return the text of an entry or label."""
    return Atspi.Text.get_text(node, 0, -1)


def is_sensitive(node):
    return node.get_state_set().contains(Atspi.StateType.SENSITIVE)


def is_showing(node):
    return node.get_state_set().contains(Atspi.StateType.SHOWING)


def is_selected(node):
    return node.get_state_set().contains(Atspi.StateType.SELECTED)


def is_focused(node):
    return node.get_state_set().contains(Atspi.StateType.FOCUSED)


class Gpredict:
    """A gpredict process with its own configuration directory."""

    def __init__(self, modules=("Amateur",), open_modules=None):
        """
        modules: names of the modules to create, copies of data/Amateur.mod
        open_modules: value for OPEN_MODULES in gpredict.cfg, or None for
                      gpredict's default
        """
        self.binary = os.environ.get("GPREDICT",
                                     os.path.join(SRCDIR, "src", "gpredict"))
        self.confdir = tempfile.mkdtemp(prefix="gpredict-ui-")
        self.process = None
        self.app = None

        gpdir = os.path.join(self.confdir, "Gpredict")
        os.makedirs(os.path.join(gpdir, "modules"))
        for name in modules:
            shutil.copy(os.path.join(SRCDIR, "data", "Amateur.mod"),
                        os.path.join(gpdir, "modules", name + ".mod"))
        if open_modules is not None:
            with open(os.path.join(gpdir, "gpredict.cfg"), "w") as cfg:
                cfg.write("[GLOBAL]\nOPEN_MODULES=%s\n" % open_modules)

    def start(self):
        # On its first start in the empty configuration directory gpredict
        # copies the default configuration (ground station, satellite data)
        # from its data directory. Take it from the source tree, so the tests
        # neither need an installed gpredict nor depend on its version.
        env = dict(os.environ,
                   XDG_CONFIG_HOME=self.confdir,
                   GPREDICT_DATA_DIR=SRCDIR,
                   GDK_BACKEND="x11",
                   LC_ALL="C",
                   LANGUAGE="C")
        env.pop("WAYLAND_DISPLAY", None)
        with open(os.path.join(self.confdir, "gpredict.out"), "w") as out:
            self.process = subprocess.Popen([self.binary], env=env,
                                            stdout=out,
                                            stderr=subprocess.STDOUT)
        try:
            self.app = wait_for(self._find_app, "gpredict to start")
            self.main_window()
        except BaseException:
            log = os.path.join(self.confdir, "Gpredict", "logs",
                               "gpredict.log")
            if os.path.exists(log):
                with open(log) as f:
                    print("gpredict.log:\n" + f.read())
            self.stop()
            raise
        return self

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(TIMEOUT)
            self.process = None
        shutil.rmtree(self.confdir, ignore_errors=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _find_app(self):
        if self.process.poll() is not None:
            raise AssertionError("gpredict exited with code %d before its "
                                 "window appeared" % self.process.returncode)
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is not None and \
                    app.get_process_id() == self.process.pid and \
                    app.get_child_count() > 0:
                return app
        return None

    def main_window(self):
        return wait_for(lambda: find(self.app, "frame"), "the main window")

    def dialog(self, title):
        return wait_for(lambda: find(self.app, "dialog", title),
                        "dialog '%s'" % title)

    def wait_dialog_closed(self, title):
        wait_for(lambda: find(self.app, "dialog", title) is None,
                 "dialog '%s' to close" % title)

    def menu(self, menu, item):
        """Select a menu item, e.g. menu("File", "Open module")."""
        menu_item = wait_for(lambda: find(self.app, "menu item", item),
                             "menu item '%s'" % item)
        click_until(find(self.app, "menu", menu),
                    lambda: is_showing(menu_item),
                    "menu item '%s' to show" % item)

        # GTK ignores clicks within 500 ms of opening a menu, taking them for
        # the release of the click that opened it
        time.sleep(0.6)
        click(menu_item)

    def module_tabs(self):
        """Return the names of the modules docked in the main window."""
        window = self.main_window()
        tabs = [tab.get_name() for tab in find_all(window, "page tab")]

        # the tab is hidden when only one module is docked, but the window
        # title shows the name of the current module
        if tabs == [""]:
            tabs = [window.get_name().split(": ", 1)[1]]

        return tabs
