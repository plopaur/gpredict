"""
UI tests for the ground tracks on the map view.

Ground tracks were not drawn in gpredict 2.4 even when they were enabled.
The map is drawn by gpredict itself, so its content is not in the
accessibility tree. The tests find the ISS and its ground track by the
colours of the default map settings instead.

The satellites move, so gpredict starts at a fixed time with frozen
satellite data, and the map looks the same in every run. At START_TIME the
ISS is over South America, away from the edges of the map, the text on it
and the other satellites of the Amateur module. The tests need libfaketime
and are skipped without it.
"""

import time
import unittest

from gi.repository import GLib

from gpredict_ui import FROZEN_SATDATA, Gpredict, Pixels, click, click_at, \
    find, is_checked, log, wait_for

ISS = 25544
START_TIME = "2026-11-01 12:00:00"

# only the ISS in the module, so its marker is the only satellite marker
ISS_ONLY = {"GLOBAL": {"SATELLITES": "%d;" % ISS}}
ISS_WITH_TRACK = {"GLOBAL": {"SATELLITES": "%d;" % ISS},
                  "MAP": {"SHOWTRACKS": "%d;" % ISS}}

# A ground track covers several thousand pixels, three orbits by default.
# Without a track no pixel of the map has the colour of the track.
MIN_TRACK_PIXELS = 500


def is_track(r, g, b):
    """
    The colour of the ground track, MAP_TRACK_COLOUR 0xFF1200 drawn with
    alpha 0xBB over the map: strongly red, little green and blue.
    """
    return r > 150 and g < 90 and b < 90 and r - g > 100


def is_satellite(r, g, b):
    """The colour of a satellite marker, MAP_SAT_COLOUR 0xF0F000."""
    return r > 220 and g > 220 and b < 60


def is_selected_satellite(r, g, b):
    """The colour of the selected satellite, MAP_SELECTED_SAT_COLOUR white."""
    return r > 240 and g > 240 and b > 240


def near(a, b, distance=3):
    return abs(a[0] - b[0]) <= distance and abs(a[1] - b[1]) <= distance


class MapHelpers:
    """Finding the ISS and its ground track on the map."""

    def gpredict(self, **kwargs):
        """Return a Gpredict at START_TIME with the frozen satellite data."""
        return Gpredict(start_time=START_TIME, satdata=FROZEN_SATDATA,
                        **kwargs)

    def find_iss(self, pixels):
        """Return the screen position of the ISS on the map, or None."""
        # the marker is a 6 x 6 square, its edges can be blended
        pos = pixels.find_block(is_satellite, 4)
        if pos is not None:
            return pos

        # Older versions draw the marker as a dot of one or two pixels. The
        # footprint around it is drawn in the same colour and centred on
        # the satellite, unless it is split at the edge of the map.
        box = pixels.bounding_box(is_satellite)
        if box is None or box[2] - box[0] > pixels.width // 2:
            return None
        return (box[0] + box[2]) // 2, (box[1] + box[3]) // 2

    def track_pixels(self, gp):
        return Pixels(gp.map_view()).count(is_track)

    def wait_for_iss(self, gp):
        """Wait until the ISS is drawn on the map, return its position."""
        # Right after the start the map is drawn small, before the window
        # has its final layout. Wait until the marker stays in place for a
        # second, the ISS moves less than a pixel in that time.
        seen = {"pos": None, "since": 0.0}

        def stable_marker():
            pos = self.find_iss(Pixels(gp.map_view()))
            now = time.monotonic()
            if pos is None or seen["pos"] is None or \
                    abs(pos[0] - seen["pos"][0]) > 2 or \
                    abs(pos[1] - seen["pos"][1]) > 2:
                seen["pos"], seen["since"] = pos, now
                return None
            return pos if now - seen["since"] >= 1.0 else None

        return wait_for(stable_marker,
                        "the yellow marker of the ISS on the map")

    def wait_for_track(self, gp):
        wait_for(lambda: self.track_pixels(gp) >= MIN_TRACK_PIXELS,
                 "the red ground track of the ISS on the map (at least %d "
                 "pixels)" % MIN_TRACK_PIXELS)
        log("%d pixels of the map have the colour of the ground track"
            % self.track_pixels(gp))

    def wait_for_no_track(self, gp):
        wait_for(lambda: self.track_pixels(gp) == 0,
                 "the ground track of the ISS to disappear from the map")

    def ground_track_item(self, gp, pos=None):
        """
        Open the menu of the ISS on the map, at pos if given, and return its
        Ground Track item.
        """
        x, y = pos or self.wait_for_iss(gp)
        click_at(x, y, "the ISS on the map", button="b3c")
        item = wait_for(lambda: find(gp.app, "check menu item",
                                     "Ground Track"),
                        "the Ground Track item in the menu of the ISS")

        # GTK ignores clicks within 500 ms of opening a menu, taking them for
        # the release of the click that opened it
        time.sleep(0.6)
        return item

    def showtracks(self, gp):
        """Return the SHOWTRACKS list in the saved Amateur.mod."""
        cfg = gp.read_module("Amateur")
        try:
            return cfg.get_integer_list("MAP", "SHOWTRACKS")
        except GLib.Error:
            return []



class GroundTrackTest(MapHelpers, unittest.TestCase):
    """Map view: ground tracks of the ISS."""

    def test_no_track_by_default(self):
        """Map view: no ground track is drawn when none is enabled."""
        with self.gpredict(module_settings=ISS_ONLY) as gp:
            self.wait_for_iss(gp)
            self.assertEqual(self.track_pixels(gp), 0,
                             "the map shows pixels in the colour of the "
                             "ground track, but no track is enabled")

    def test_track_from_mod_file(self):
        """Map view: a ground track enabled in the .mod file is drawn."""
        with self.gpredict(module_settings=ISS_WITH_TRACK) as gp:
            self.wait_for_iss(gp)
            self.wait_for_track(gp)

    def test_enable_track(self):
        """Map view: enabling Ground Track draws it and saves it in .mod."""
        with self.gpredict(module_settings=ISS_ONLY) as gp:
            item = self.ground_track_item(gp)
            self.assertFalse(is_checked(item),
                             "Ground Track is checked, but no track is "
                             "enabled in the .mod file")
            click(item)
            self.wait_for_track(gp)

            gp.quit()
            log("SHOWTRACKS in Amateur.mod: %s" % self.showtracks(gp))
            self.assertEqual(self.showtracks(gp), [ISS],
                             "the enabled ground track was not saved in "
                             "[MAP] SHOWTRACKS of Amateur.mod")

    def test_disable_track(self):
        """Map view: disabling Ground Track removes it and its .mod entry."""
        with self.gpredict(module_settings=ISS_WITH_TRACK) as gp:
            self.wait_for_track(gp)
            item = self.ground_track_item(gp)
            self.assertTrue(is_checked(item),
                            "Ground Track is not checked, but the track is "
                            "enabled in the .mod file")
            click(item)
            self.wait_for_no_track(gp)

            gp.quit()
            log("SHOWTRACKS in Amateur.mod: %s" % self.showtracks(gp))
            self.assertEqual(self.showtracks(gp), [],
                             "the disabled ground track is still in "
                             "[MAP] SHOWTRACKS of Amateur.mod")


class GroundTrackSequenceTest(MapHelpers, unittest.TestCase):
    """Map view: ground track of the ISS in the full Amateur module."""

    def wait_for_markers(self, gp):
        """
        Wait until the yellow satellite markers on the map stay in place for
        a second, return their screen positions.
        """
        seen = {"markers": None, "since": 0.0}

        def stable_markers():
            markers = Pixels(gp.map_view()).find_blocks(is_satellite, 4)
            now = time.monotonic()
            old = seen["markers"]
            if not markers or old is None or len(markers) != len(old) or \
                    not all(any(near(m, o) for o in old) for m in markers):
                seen["markers"], seen["since"] = markers, now
                return None
            return markers if now - seen["since"] >= 1.0 else None

        markers = wait_for(stable_markers,
                           "the yellow satellite markers on the map")
        log("yellow satellite markers at %s" % markers)
        return markers

    def select_iss(self, gp):
        """
        Select the ISS in the module menu and return its position on the
        map, where its marker changes from yellow to white.
        """
        # select another satellite first, so the ISS is not selected and its
        # marker is yellow before it is selected
        gp.module_menu("Select satellite", "AO-73")
        wait_for(lambda: find(gp.main_window(), "label", "AO-73"),
                 "AO-73 in the satellite details")
        before = self.wait_for_markers(gp)

        gp.module_menu("Select satellite", "ISS")
        wait_for(lambda: find(gp.main_window(), "label", "ISS"),
                 "ISS in the satellite details")

        def iss_marker():
            pixels = Pixels(gp.map_view())
            after = pixels.find_blocks(is_satellite, 4)
            gone = [b for b in before if not any(near(b, a) for a in after)]
            if len(gone) != 1:
                return None
            x, y = gone[0]
            if not is_selected_satellite(*pixels.rgb(x - pixels.x,
                                                     y - pixels.y)):
                return None
            return gone[0]

        pos = wait_for(iss_marker, "the marker of the ISS to turn from "
                       "yellow to white, the colour of the selected "
                       "satellite")
        log("the ISS is at %d, %d" % pos)
        return pos

    def toggle_track(self, gp, pos, checked_before):
        """Toggle Ground Track in the menu of the ISS at pos."""
        item = self.ground_track_item(gp, pos)
        self.assertEqual(is_checked(item), checked_before,
                         "Ground Track should be %s before the click"
                         % ("checked" if checked_before else "unchecked"))
        click(item)
        if checked_before:
            self.wait_for_no_track(gp)
        else:
            self.wait_for_track(gp)

    def test_track_on_off_on_and_restart(self):
        """Map view: Ground Track on, off, on, saved and restored."""
        with self.gpredict() as gp:
            pos = self.select_iss(gp)
            self.assertEqual(self.track_pixels(gp), 0,
                             "a ground track is drawn before any is enabled")

            self.toggle_track(gp, pos, checked_before=False)
            self.toggle_track(gp, pos, checked_before=True)
            self.toggle_track(gp, pos, checked_before=False)

            gp.quit()
            log("SHOWTRACKS in Amateur.mod: %s" % self.showtracks(gp))
            self.assertEqual(self.showtracks(gp), [ISS],
                             "the enabled ground track of the ISS was not "
                             "saved in [MAP] SHOWTRACKS of Amateur.mod")

            # start again with the saved Amateur.mod
            gp.start()
            self.wait_for_track(gp)
            pos = self.select_iss(gp)
            item = self.ground_track_item(gp, pos)
            self.assertTrue(is_checked(item),
                            "Ground Track of the ISS is not checked after "
                            "the restart, although it was saved")


if __name__ == "__main__":
    unittest.main()
