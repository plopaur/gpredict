"""
Run the UI tests with unittest, see run-ui-tests.sh.

Takes the same arguments as "python3 -m unittest". In addition to the
unittest output, it tells gpredict_ui which test is running, so screenshots
are named after the test, and when running in GitHub Actions it reports each
failure as an error annotation on the line of the test that failed.
"""

import os
import traceback
import unittest

import gpredict_ui


def _escape(text, prop=False):
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if prop:
        text = text.replace(":", "%3A").replace(",", "%2C")
    return text


def _annotate(stream, test, err):
    """Print a GitHub Actions error annotation for a failed test."""
    exc_type, exc, tb = err
    frames = traceback.extract_tb(tb)

    # the innermost frame in a test file is the line of the test that failed
    location = ""
    for frame in reversed(frames):
        if os.path.basename(frame.filename).startswith("test_"):
            workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
            path = os.path.relpath(frame.filename, workspace)
            location = "file=%s,line=%d," % (_escape(path, True),
                                              frame.lineno)
            break

    title = "UI test %s failed" % test.id().rsplit(".", 1)[-1]
    summary = test.shortDescription()
    message = "%s%s: %s\nSee the job log for the steps, the UI state and " \
        "gpredict's log." % (summary + "\n" if summary else "",
                             exc_type.__name__, exc)
    stream.write("::error %stitle=%s::%s\n" % (
        location, _escape(title, True), _escape(message)))
    stream.flush()


class Result(unittest.TextTestResult):

    def startTest(self, test):
        gpredict_ui.current_test = test.id()
        super().startTest(test)

    def _report(self, test, err):
        # with -b the output of a failed test is part of the report below;
        # do not also copy it to stdout, where the service messages go
        self._mirrorOutput = False
        if gpredict_ui.GITHUB_ACTIONS:
            _annotate(self.stream, test, err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._report(test, err)

    def addError(self, test, err):
        super().addError(test, err)
        self._report(test, err)


class Runner(unittest.TextTestRunner):
    # unittest passes -v and -b only to a runner given as a class
    resultclass = Result

    def __init__(self, stream=None, **kwargs):
        # run-ui-tests.sh sends stdout and stderr of the D-Bus and AT-SPI
        # services to a log and passes the descriptor for the report
        if stream is None:
            fd = int(os.environ.get("UI_TEST_REPORT_FD", "2"))
            stream = os.fdopen(os.dup(fd), "w", buffering=1)
        super().__init__(stream=stream, **kwargs)


if __name__ == "__main__":
    unittest.main(module=None, testRunner=Runner)
