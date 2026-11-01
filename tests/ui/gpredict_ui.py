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

import datetime
import glob
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402

TIMEOUT = 10
SRCDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Satellite data frozen for the tests, so updates of data/satdata do not
# move the satellites. The TLEs have their epoch on 2026-11-01.
FROZEN_SATDATA = os.path.join(TESTDATA, "satdata")
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


def faketime_library():
    """
    Return the path of libfaketime, or None if it is not installed.
    UI_TEST_FAKETIME_LIB overrides the search.
    """
    path = os.environ.get("UI_TEST_FAKETIME_LIB")
    if path:
        return path if os.path.exists(path) else None
    for pattern in ("/usr/lib/*/faketime/libfaketime.so.1",
                    "/usr/lib/faketime/libfaketime.so.1",
                    "/usr/local/lib/faketime/libfaketime.so.1"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


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
BUTTON_ROLES = ("button", "push button")
MENU_ROLES = ("menu", "menu item", "check menu item", "radio menu item")


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


def click_at(x, y, what, button="b1c"):
    """Click the screen position x, y. Use button="b3c" for a right click."""
    log("%s at %d, %d on %s" % ("right click" if button.startswith("b3")
                                else "click", x, y, what))
    Atspi.generate_mouse_event(x, y, button)


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


def set_value(node, value):
    """Set the value of a spin button or slider."""
    log("set %s to %s" % (describe(node), value))
    if not Atspi.Value.set_current_value(node, value):
        raise AssertionError("Could not set %s to %s" % (describe(node),
                                                         value))


def move_window(window, x, y):
    """
    Move a top level window to the screen position x, y. Without a window
    manager new windows open in the top left corner, over the main window.
    """
    log("move %s '%s' to %d, %d" % (window.get_role_name(), window.get_name(),
                                     x, y))
    Atspi.Component.set_position(window, x, y, Atspi.CoordType.SCREEN)
    wait_for(lambda: window.get_position(Atspi.CoordType.SCREEN).x == x,
             "%s '%s' to move" % (window.get_role_name(), window.get_name()),
             quiet=True)


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


def is_checked(node):
    return node.get_state_set().contains(Atspi.StateType.CHECKED)


def _screen_pixbuf(x=0, y=0, width=None, height=None):
    """Return a GdkPixbuf with the given area of the X display."""
    # Gdk opens its display when imported. Without this it can open the
    # desktop's Wayland display instead of the private X display.
    os.environ["GDK_BACKEND"] = "x11"
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    root = Gdk.get_default_root_window()
    if width is None:
        width, height = root.get_width(), root.get_height()
    return Gdk.pixbuf_get_from_window(root, x, y, width, height)


def save_screenshot(path):
    """Save a screenshot of the X display to path, return True on success."""
    try:
        _screen_pixbuf().savev(path, "png", [], [])
        return True
    except Exception as err:   # a screenshot must never hide the failure
        print("Could not save a screenshot: %s" % err)
        return False


class Pixels:
    """
    The pixels of a widget as shown on the screen.

    For widgets that draw their content themselves, like the map, whose
    content is not in the accessibility tree.
    """

    def __init__(self, node):
        ext = node.get_extents(Atspi.CoordType.SCREEN)
        self.x, self.y = ext.x, ext.y
        self.width, self.height = ext.width, ext.height
        pixbuf = _screen_pixbuf(ext.x, ext.y, ext.width, ext.height)
        self._data = pixbuf.read_pixel_bytes().get_data()
        self._stride = pixbuf.get_rowstride()
        self._channels = pixbuf.get_n_channels()

    def rgb(self, x, y):
        """Return the colour of the pixel x, y within the widget."""
        i = y * self._stride + x * self._channels
        return self._data[i], self._data[i + 1], self._data[i + 2]

    def count(self, match):
        """Return the number of pixels whose colour matches match(r, g, b)."""
        return sum(1 for y in range(self.height) for x in range(self.width)
                   if match(*self.rgb(x, y)))

    def bounding_box(self, match):
        """
        Return the screen positions (left, top, right, bottom) of the
        smallest rectangle around all pixels whose colour matches
        match(r, g, b), or None if no pixel matches.
        """
        xs, ys = [], []
        for y in range(self.height):
            for x in range(self.width):
                if match(*self.rgb(x, y)):
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return (self.x + min(xs), self.y + min(ys),
                self.x + max(xs), self.y + max(ys))

    def find_blocks(self, match, size):
        """
        Return the screen positions of the centres of all size x size
        blocks of pixels whose colours all match match(r, g, b). Blocks that
        overlap count once.
        """
        found = []
        for y in range(self.height - size + 1):
            for x in range(self.width - size + 1):
                if any(abs(x - fx) < 2 * size and abs(y - fy) < 2 * size
                       for fx, fy in found):
                    continue
                if all(match(*self.rgb(x + i, y + j))
                       for j in range(size) for i in range(size)):
                    found.append((x, y))
        return [(self.x + x + size // 2, self.y + y + size // 2)
                for x, y in found]

    def find_block(self, match, size):
        """
        Return the screen position of the centre of the first size x size
        block of pixels whose colours all match match(r, g, b), or None.
        """
        for y in range(self.height - size + 1):
            for x in range(self.width - size + 1):
                if all(match(*self.rgb(x + i, y + j))
                       for j in range(size) for i in range(size)):
                    return self.x + x + size // 2, self.y + y + size // 2
        return None


class Gpredict:
    """A gpredict process with its own configuration directory."""

    def __init__(self, modules=("Amateur",), open_modules=None,
                 module_settings=None, start_time=None, satdata=None):
        """
        modules: names of the modules to create, copies of data/Amateur.mod
        open_modules: value for OPEN_MODULES in gpredict.cfg, or None for
                      gpredict's default
        module_settings: settings to change in the modules, as
                         {section: {key: value}}, e.g.
                         {"MAP": {"SHOWTRACKS": "25544;"}}
        start_time: UTC time at which gpredict starts, e.g.
                    "2026-11-01 12:00:00", or None for the current time.
                    The time runs on from there. Uses libfaketime; the test
                    is skipped if it is not installed.
        satdata: directory with .sat files to use instead of the satellite
                 data in data/satdata, e.g. FROZEN_SATDATA
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
            if module_settings:
                cfg = self.read_module(name)
                for section, values in module_settings.items():
                    for key, value in values.items():
                        cfg.set_value(section, key, value)
                cfg.save_to_file(self.module_file(name))
        if open_modules is not None:
            with open(os.path.join(gpdir, "gpredict.cfg"), "w") as cfg:
                cfg.write("[GLOBAL]\nOPEN_MODULES=%s\n" % open_modules)

        # gpredict only creates the satellite data from data/satdata if
        # there are no .sat files yet
        if satdata is not None:
            os.makedirs(os.path.join(gpdir, "satdata"))
            for sat in glob.glob(os.path.join(satdata, "*.sat")):
                shutil.copy(sat, os.path.join(gpdir, "satdata"))
        self.start_time = start_time

        self.setup = "modules %s" % ", ".join(modules)
        if open_modules is not None:
            self.setup += ", OPEN_MODULES=%s" % open_modules
        for section, values in (module_settings or {}).items():
            for key, value in values.items():
                self.setup += ", [%s] %s=%s" % (section, key, value)
        if satdata is not None:
            self.setup += ", satellites from %s" % os.path.relpath(satdata,
                                                                   SRCDIR)
        if start_time is not None:
            self.setup += ", starting at %s UTC" % start_time

    def module_file(self, name):
        return os.path.join(self.confdir, "Gpredict", "modules",
                            name + ".mod")

    def read_module(self, name):
        """Return the .mod file of a module as a GLib.KeyFile."""
        cfg = GLib.KeyFile()
        cfg.load_from_file(self.module_file(name),
                           GLib.KeyFileFlags.KEEP_COMMENTS)
        return cfg

    def start(self):
        global _current, _start_time

        faketime = None
        if self.start_time is not None:
            faketime = faketime_library()
            if faketime is None:
                shutil.rmtree(self.confdir, ignore_errors=True)
                msg = ("this test needs libfaketime to start gpredict at a "
                       "fixed time (apt install faketime)")
                # in CI a missing package must not go unnoticed
                if os.environ.get("CI") == "true":
                    raise AssertionError(msg)
                raise unittest.SkipTest(msg)

        _current = self
        _start_time = time.monotonic()
        log("start gpredict with " + self.setup)

        # On its first start in the empty configuration directory gpredict
        # copies the default configuration (ground station, satellite data)
        # from its data directory. Take it, and the maps, logos and icons,
        # from the source tree, so the tests neither need an installed
        # gpredict nor depend on its version.
        env = dict(os.environ,
                   XDG_CONFIG_HOME=self.confdir,
                   GPREDICT_DATA_DIR=SRCDIR,
                   GPREDICT_PIXMAPS_DIR=os.path.join(SRCDIR, "pixmaps"),
                   GDK_BACKEND="x11",
                   LC_ALL="C",
                   LANGUAGE="C")
        env.pop("WAYLAND_DISPLAY", None)
        if faketime is not None:
            # start at start_time and let the time run on from there; the
            # monotonic clock stays real for the GTK main loop
            env.update(LD_PRELOAD=faketime,
                       FAKETIME="@" + self.start_time,
                       FAKETIME_DONT_FAKE_MONOTONIC="1",
                       TZ="UTC")
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

    def quit(self):
        """Quit gpredict with File > Quit, so it saves its configuration."""
        self.menu("File", "Quit")
        try:
            code = self.process.wait(TIMEOUT)
        except subprocess.TimeoutExpired:
            raise _timeout_error("gpredict to quit", TIMEOUT)
        log("gpredict quit with code %d" % code)
        self.process = None

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

    def map_view(self):
        """Return the map of the current module."""
        def largest_drawing_area():
            areas = find_all(self.main_window(), "drawing area")
            if not areas:
                return None
            return max(areas, key=lambda a: a.get_size().x * a.get_size().y)

        return wait_for(largest_drawing_area, "the map view", quiet=True)

    def main_window(self):
        def find_main_window():
            return next((w for w in self.windows()
                         if w.get_role_name() == "frame" and
                         w.get_name().startswith("Gpredict")), None)

        return wait_for(find_main_window, "the main window", quiet=True)

    def windows(self):
        """Return the top level windows of gpredict."""
        windows = []
        for i in range(self.app.get_child_count()):
            win = self.app.get_child_at_index(i)
            if win is not None:
                windows.append(win)
        return windows

    def window(self, name):
        """Wait for the top level window whose title starts with name."""
        return wait_for(lambda: next((w for w in self.windows()
                                      if w.get_name().startswith(name)),
                                     None),
                        "window '%s'" % name)

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

    def module_menu(self, *path):
        """
        Select an item in the menu of the module button in the top right
        corner of the current module, e.g. module_menu("Select satellite",
        "ISS").
        """
        log("select module menu %s" % " > ".join(path))

        def menu_button():
            buttons = [b for b in walk(self.main_window())
                       if b.get_role_name() in BUTTON_ROLES]
            if not buttons:
                return None
            # the module button is the topmost button, in the module header
            return min(buttons, key=lambda b: b.get_position(
                Atspi.CoordType.SCREEN).y)

        def showing_item(name):
            return next((n for n in walk(self.app)
                         if n.get_role_name() in MENU_ROLES and
                         n.get_name() == name and is_showing(n)), None)

        button = wait_for(menu_button, "the module menu button", quiet=True)
        item = click_until(button, lambda: showing_item(path[0]),
                           "module menu with item '%s'" % path[0])
        for name in path[1:]:
            # GTK ignores clicks within 500 ms of opening a menu
            time.sleep(0.6)
            click(item)
            item = wait_for(lambda: showing_item(name),
                            "menu item '%s'" % name)
        time.sleep(0.6)
        click(item)

    def module_time(self):
        """
        Return the time shown in the header of the current module as a
        datetime, or None if it is not shown.
        """
        for node in walk(self.main_window()):
            if node.get_role_name() == "label" and re.fullmatch(
                    r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", node.get_name()):
                return datetime.datetime.strptime(node.get_name(),
                                                  "%Y/%m/%d %H:%M:%S")
        return None

    def module_tabs(self):
        """Return the names of the modules docked in the main window."""
        window = self.main_window()
        tabs = [tab.get_name() for tab in find_all(window, "page tab")]

        # the tab is hidden when only one module is docked, but the window
        # title shows the name of the current module
        if tabs == [""]:
            tabs = [window.get_name().split(": ", 1)[1]]

        return tabs
