"""
UI tests for the Time Controller of a module.

The tests use the time controls that work through the accessibility
interface: the Stop, Play forward and Reset buttons and the spin buttons
for the time of day. The calendar for the date offers no accessible value,
so it is not used.
"""

import datetime
import time
import unittest

from gpredict_ui import Gpredict, click, find, find_all, log, move_window, \
    set_value, wait_for

SPIN_BUTTONS = {
    "hour": "Use this control to set the hour",
    "min": "Use this control to set the minutes",
    "sec": "Use this control to set the seconds",
    "msec": "Use this control to set the milliseconds",
}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class TimeControllerTest(unittest.TestCase):
    """Module menu > Time Controller."""

    def open_time_controller(self, gp):
        gp.module_menu("Time Controller")
        window = gp.window("Time Controller")
        # move it away from the module, it opens over it
        move_window(window, 800, 100)
        return window

    def button(self, window, description):
        """Return the button with the given tooltip, e.g. "Stop"."""
        found = [b for b in find_all(window, "radio button")
                 if b.get_description() == description]
        self.assertTrue(found, "no '%s' button in the Time Controller"
                        % description)
        return found[0]

    def spin_button(self, window, name):
        found = [s for s in find_all(window, "spin button")
                 if s.get_description() == SPIN_BUTTONS[name]]
        self.assertTrue(found, "no spin button for the %s in the Time "
                        "Controller" % name)
        return found[0]

    def wait_for_mode(self, window, mode):
        """Wait until the Time Controller shows mode, e.g. "Real-Time"."""
        wait_for(lambda: find(window, "label", mode),
                 "the Time Controller to show '%s'" % mode)

    def wait_for_module_time(self, gp, check, what):
        def matching_time():
            shown = gp.module_time()
            return shown if shown is not None and check(shown) else None

        shown = wait_for(matching_time, "the module time to show " + what)
        log("the module shows %s" % shown)
        return shown

    def test_manual_time(self):
        """Time Controller: Stop and the spin buttons set a fixed time."""
        with Gpredict() as gp:
            window = self.open_time_controller(gp)
            self.wait_for_mode(window, "Real-Time")

            click(self.button(window, "Stop"))
            self.wait_for_mode(window, "Manual Control")

            set_value(self.spin_button(window, "hour"), 12)
            set_value(self.spin_button(window, "min"), 34)
            set_value(self.spin_button(window, "sec"), 56)
            set_value(self.spin_button(window, "msec"), 0)
            shown = self.wait_for_module_time(
                gp, lambda t: t.time() == datetime.time(12, 34, 56),
                "12:34:56")

            # in manual control the time stands still
            time.sleep(3)
            self.assertEqual(gp.module_time(), shown,
                             "the module time changed in manual control")

            # play forward runs the time on from the time that was set
            click(self.button(window, "Play forward"))
            self.wait_for_mode(window, "Simulated Real-Time")
            self.wait_for_module_time(
                gp, lambda t: shown < t < shown + datetime.timedelta(
                    seconds=30),
                "a time running on from %s" % shown)

    def test_reset(self):
        """Time Controller: Reset returns to the current time."""
        with Gpredict() as gp:
            window = self.open_time_controller(gp)
            click(self.button(window, "Stop"))
            self.wait_for_mode(window, "Manual Control")
            set_value(self.spin_button(window, "hour"),
                      (utc_now().hour + 12) % 24)
            self.wait_for_module_time(
                gp, lambda t: abs(t - utc_now()) > datetime.timedelta(
                    hours=1),
                "a time far from the current time")

            click(self.button(window, "Play forward"))
            click(find(window, "button", "Reset"))
            self.wait_for_mode(window, "Real-Time")
            self.wait_for_module_time(
                gp, lambda t: abs(t - utc_now()) < datetime.timedelta(
                    seconds=10),
                "the current time (UTC %s)" % utc_now().strftime("%H:%M:%S"))


if __name__ == "__main__":
    unittest.main()
