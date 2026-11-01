"""
Helpers for driving gpredict through the accessibility interface (AT-SPI).

Widgets are looked up in the accessibility tree by role and name. Clicks and
key presses are sent as real input events, because activating a widget
through AT-SPI blocks while gpredict runs a modal dialog.

gpredict runs with a temporary configuration directory, filled with the
default configuration from the source tree, so the tests never touch or
depend on the user's configuration. They should run on a private X display,
see run-ui-tests.sh.

Every action is logged as a step, naming the widget and the window or
dialog it is in. When a test fails, the steps are shown together with the
windows gpredict has open at that moment, its log and, if UI_TEST_ARTIFACTS
names a directory, a screenshot saved there.
"""

import os
import shutil
import subprocess
import tempfile
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402

TIMEOUT = 10
SRCDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

# id of the running test, set by run_tests.py, used to name screenshots
current_test = None

# the gpredict instance of the running test, used to describe the UI
# when waiting for something times out
_current = None
_start_time = time.monotonic()


def log(msg):
    """Log a test step. The output is only shown when the test fails."""
    print("  [%5.1fs] %s" % (time.monotonic() - _start_time, msg),
          flush=True)


def print_block(title, text):
    """Print a block of output, collapsible in the GitHub Actions log."""
    if GITHUB_ACTIONS:
        print("::group::" + title)
        print(text.rstrip("\n"))
        print("::endgroup::")
    else:
        print("----- %s -----" % title)
        print(text.rstrip("\n"))
        print("----- end of %s -----" % title)


def _timeout_error(what, timeout):
    msg = "Timed out after %g s waiting for %s" % (timeout, what)
    if _current is not None:
        msg += "\n" + "\n".join(_current.describe_ui())
    return AssertionError(msg)


def wait_for(func, what, timeout=TIMEOUT, quiet=False):
    """
    Call func until it returns a true value and return that value.

    what describes what is waited for, e.g. "dialog 'Select a module'". It is
    logged when the wait succeeds and is part of the error when it times out.
    """
    end = time.monotonic() + timeout
    while True:
        result = func()
        if result:
            if not quiet:
                log("found " + what)
            return result
        if time.monotonic() > end:
            raise _timeout_error(what, timeout)
        time.sleep(0.1)


def walk(node):
    """Yield node and all nodes below it."""
    yield node
    for i in range(node.get_child_count()):
        child = node.get_child_at_index(i)
        if child is not None:
            yield from walk(child)


def find_all(node, role, name=None):
    """Return all nodes below node with the given role and name."""
    return [n for n in walk(node)
            if n.get_role_name() == role and name in (None, n.get_name())]


def find(node, role, name=None):
    """Return the first node below node with the given role and name."""
    found = find_all(node, role, name)
    return found[0] if found else None


WINDOW_ROLES = ("frame", "dialog", "alert", "window", "file chooser")


def describe(node):
    """Describe node and its window, e.g. "button 'OK' in dialog 'Open'"."""
    try:
        desc = "%s '%s'" % (node.get_role_name(), node.get_name())
        parent = node.get_parent()
        while parent is not None:
            if parent.get_role_name() in WINDOW_ROLES:
                return "%s in %s '%s'" % (desc, parent.get_role_name(),
                                         parent.get_name())
            parent = parent.get_parent()
        return desc
    except GLib.Error:
        return "a widget that no longer exists"


def click(node, button="b1c"):
    """Click the centre of node. Use button="b1d" for a double click."""
    log("click " + describe(node))
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
            result = wait_for(func, what, timeout=1, quiet=True)
            log("found " + what)
            return result
        except AssertionError:
            pass
    raise _timeout_error("%s after %d clicks" % (what, attempts), attempts)


def type_text(text):
    """Type text into the widget that has the keyboard focus."""
    log("type '%s'" % text)
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


def save_screenshot(path):
    """Save a screenshot of the X display to path, return True on success."""
    try:
        # Gdk opens its display when imported. Without this it can open the
        # desktop's Wayland display instead of the private X display.
        os.environ["GDK_BACKEND"] = "x11"
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk

        root = Gdk.get_default_root_window()
        pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(),
                                            root.get_height())
        pixbuf.savev(path, "png", [], [])
        return True
    except Exception as err:   # a screenshot must never hide the failure
        print("Could not save a screenshot: %s" % err)
        return False


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

        self.setup = "modules %s" % ", ".join(modules)
        if open_modules is not None:
            self.setup += ", OPEN_MODULES=%s" % open_modules

    def start(self):
        global _current, _start_time

        _current = self
        _start_time = time.monotonic()
        log("start gpredict with " + self.setup)

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
            self.app = wait_for(self._find_app, "gpredict in the "
                                "accessibility tree")
            self.main_window()
        except BaseException:
            self.report_failure()
            self.stop()
            raise
        return self

    def stop(self):
        global _current

        if self.process is not None:
            self.process.terminate()
            self.process.wait(TIMEOUT)
            self.process = None
        shutil.rmtree(self.confdir, ignore_errors=True)
        _current = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.report_failure()
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

    def describe_ui(self):
        """Return lines describing the windows gpredict has open."""
        if self.process is not None and self.process.poll() is not None:
            return ["gpredict has exited with code %d"
                    % self.process.returncode]
        if self.app is None:
            return ["gpredict has not appeared in the accessibility tree"]

        lines = ["Windows open in gpredict:"]
        try:
            focus = None
            for i in range(self.app.get_child_count()):
                win = self.app.get_child_at_index(i)
                if win is None:
                    continue
                role = win.get_role_name()
                line = "  %s '%s'" % (role, win.get_name())
                if role == "frame":
                    tabs = [t.get_name() for t in find_all(win, "page tab")]
                    if tabs and tabs != [""]:
                        line += ", module tabs: " + ", ".join(tabs)
                lines.append(line)

                if role != "frame":
                    texts = [text_of(n) for n in find_all(win, "label")]
                    for text in [t for t in texts if t.strip()][:10]:
                        lines.append("    label: " + text.replace("\n", " "))
                    buttons = [b.get_name() for b in
                               find_all(win, "push button")]
                    if buttons:
                        lines.append("    buttons: " + ", ".join(buttons))

                for node in walk(win):
                    if focus is None and is_focused(node):
                        focus = node
            lines.append("Keyboard focus: " +
                         (describe(focus) if focus else "none"))
        except GLib.Error as err:
            lines.append("  (could not read the accessibility tree: %s)" % err)
        return lines

    def report_failure(self):
        """Print the UI state and gpredict's logs, save a screenshot."""
        print("\n".join(["", "UI state at the failure:"] + self.describe_ui()))

        artifacts = os.environ.get("UI_TEST_ARTIFACTS")
        name = current_test or "gpredict-%d" % time.time()
        if artifacts:
            os.makedirs(artifacts, exist_ok=True)
            png = os.path.join(artifacts, name + ".png")
            if save_screenshot(png):
                print("Screenshot: " + png)

        for title, path in (("gpredict.log", os.path.join(
                                self.confdir, "Gpredict", "logs",
                                "gpredict.log")),
                            ("gpredict output", os.path.join(
                                self.confdir, "gpredict.out"))):
            if not os.path.exists(path):
                continue
            with open(path, errors="replace") as f:
                text = f.read()
            if artifacts:
                shutil.copy(path, os.path.join(
                    artifacts, "%s.%s" % (name, os.path.basename(path))))
            if text.strip():
                print_block(title, text)

    def main_window(self):
        return wait_for(lambda: find(self.app, "frame"), "the main window",
                        quiet=True)

    def dialog(self, title):
        return wait_for(lambda: find(self.app, "dialog", title),
                        "dialog '%s'" % title)

    def wait_dialog_closed(self, title):
        wait_for(lambda: find(self.app, "dialog", title) is None,
                 "dialog '%s' closed" % title, quiet=True)
        log("dialog '%s' closed" % title)

    def menu(self, menu, item):
        """Select a menu item, e.g. menu("File", "Open module")."""
        log("select menu %s > %s" % (menu, item))
        menu_item = wait_for(lambda: find(self.app, "menu item", item),
                             "menu item '%s'" % item, quiet=True)
        click_until(find(self.app, "menu", menu),
                    lambda: is_showing(menu_item),
                    "menu %s open with item '%s'" % (menu, item))

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
