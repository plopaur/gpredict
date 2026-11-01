#!/bin/sh
#
# Run the UI tests on a private Xvfb display with a private D-Bus session, so
# the simulated clicks and key presses cannot reach the desktop.
#
# Usage: run-ui-tests.sh [path/to/gpredict] [unittest arguments]
#
# The output of a test (its steps, the UI state and gpredict's log) is only
# shown when it fails. Screenshots and logs of failed tests are saved in
# $UI_TEST_ARTIFACTS, by default ./ui-test-results.
#
# Exits with 77 (skipped) if Xvfb is not installed.

set -e

here=$(cd "$(dirname "$0")" && pwd)

if [ -n "$1" ] && [ -x "$1" ]; then
    GPREDICT=$(realpath "$1")
    shift
else
    GPREDICT="$here/../../src/gpredict"
fi
export GPREDICT

if [ $# -eq 0 ]; then
    set -- discover -s "$here" -v -b
fi

if [ -z "$UI_TEST_ARTIFACTS" ]; then
    UI_TEST_ARTIFACTS="$PWD/ui-test-results"
    rm -rf "$UI_TEST_ARTIFACTS"
fi
export UI_TEST_ARTIFACTS

if ! command -v Xvfb >/dev/null; then
    echo "The UI tests need Xvfb (apt install xvfb), skipping." >&2
    exit 77
fi

tmp=$(mktemp -d)
trap 'kill $xpid 2>/dev/null; rm -rf "$tmp"' EXIT

# let the X server pick a free display and report its number
Xvfb -screen 0 1280x800x24 -displayfd 3 -nolisten tcp \
    3>"$tmp/display" 2>"$tmp/x.log" &
xpid=$!
for i in $(seq 50); do
    [ -s "$tmp/display" ] && break
    sleep 0.1
done
if [ ! -s "$tmp/display" ]; then
    cat "$tmp/x.log" >&2
    echo "Could not start Xvfb" >&2
    exit 1
fi
display=$(cat "$tmp/display")

# Xvfb can report its display number before it accepts connections, so wait
# until a client can connect, or the first test fails to open the display
connect='import socket, sys
s = socket.socket(socket.AF_UNIX)
s.connect("/tmp/.X11-unix/X" + sys.argv[1])'
for i in $(seq 50); do
    python3 -c "$connect" "$display" 2>/dev/null && break
    sleep 0.1
done
if ! python3 -c "$connect" "$display" 2>/dev/null; then
    cat "$tmp/x.log" >&2
    echo "Xvfb does not accept connections on display :$display" >&2
    exit 1
fi

# The D-Bus and AT-SPI services of the session print status messages. Keep
# them out of the test report, which goes to descriptor 3, and show them
# only on a failure.
status=0
DISPLAY=:$display GIO_USE_VFS=local UI_TEST_REPORT_FD=3 \
    env -u WAYLAND_DISPLAY \
    dbus-run-session -- python3 "$here/run_tests.py" "$@" \
    3>&1 >"$tmp/session.log" 2>&1 || status=$?
if [ $status -ne 0 ] && [ -s "$tmp/session.log" ]; then
    echo "----- stderr of the test session -----"
    cat "$tmp/session.log"
fi
exit $status
