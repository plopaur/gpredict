## Process this file with automake to produce Makefile.in

AM_CPPFLAGS = @PACKAGE_CFLAGS@ -I$(top_srcdir)/src

check_PROGRAMS = test-mod-mgr test-sgp4 test-sdp4

TESTS = $(check_PROGRAMS)

## test-mod-mgr.c includes mod-mgr.c to reach its internal state
test_mod_mgr_SOURCES = test-mod-mgr.c
EXTRA_test_mod_mgr_DEPENDENCIES = $(top_srcdir)/src/mod-mgr.c
test_mod_mgr_LDADD = @PACKAGE_LIBS@

## SGP4/SDP4 propagator tests. The library sources are compiled again with
## per-target flags, so the objects do not clash with the ones in src/.
SGPSDP_SRC = \
	../src/sgpsdp/sgp4sdp4.c \
	../src/sgpsdp/sgp4sdp4.h \
	../src/sgpsdp/sgp_in.c   \
	../src/sgpsdp/sgp_math.c \
	../src/sgpsdp/sgp_obs.c  \
	../src/sgpsdp/sgp_time.c \
	../src/sgpsdp/solar.c

SGPSDP_CPPFLAGS = $(AM_CPPFLAGS) -I$(top_srcdir)/src/sgpsdp \
	-DTLE_DIR=\"$(abs_srcdir)/sgpsdp\"

test_sgp4_SOURCES = sgpsdp/test-sgp4.c $(SGPSDP_SRC)
test_sgp4_CPPFLAGS = $(SGPSDP_CPPFLAGS)
test_sgp4_LDADD = @PACKAGE_LIBS@ -lm

test_sdp4_SOURCES = sgpsdp/test-sdp4.c $(SGPSDP_SRC)
test_sdp4_CPPFLAGS = $(SGPSDP_CPPFLAGS)
test_sdp4_LDADD = @PACKAGE_LIBS@ -lm

## The UI tests drive gpredict on a private Xvfb display. They are not part
## of "make check" because they need Xvfb and AT-SPI.
check-ui: all
	$(MAKE) -C $(top_builddir)/src
	$(srcdir)/ui/run-ui-tests.sh $(abs_top_builddir)/src/gpredict

clean-local:
	rm -rf ui-test-results

.PHONY: check-ui

EXTRA_DIST = \
	sgpsdp/test-sgp4.tle  \
	sgpsdp/test-sdp4.tle  \
	ui/gpredict_ui.py     \
	ui/run-ui-tests.sh    \
	ui/run_tests.py       \
	ui/test_modules.py
