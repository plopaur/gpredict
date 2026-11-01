## Process this file with automake to produce Makefile.in

AM_CPPFLAGS = @PACKAGE_CFLAGS@ -I$(top_srcdir)/src

check_PROGRAMS = test-mod-mgr

TESTS = $(check_PROGRAMS)

## test-mod-mgr.c includes mod-mgr.c to reach its internal state
test_mod_mgr_SOURCES = test-mod-mgr.c
EXTRA_test_mod_mgr_DEPENDENCIES = $(top_srcdir)/src/mod-mgr.c
test_mod_mgr_LDADD = @PACKAGE_LIBS@

## The UI tests drive gpredict on a private Xvfb display. They are not part
## of "make check" because they need Xvfb and AT-SPI.
check-ui: all
	$(MAKE) -C $(top_builddir)/src
	$(srcdir)/ui/run-ui-tests.sh $(abs_top_builddir)/src/gpredict

.PHONY: check-ui

EXTRA_DIST = \
	ui/gpredict_ui.py     \
	ui/run-ui-tests.sh    \
	ui/test_modules.py
