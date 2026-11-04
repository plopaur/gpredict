desktopdir = $(datadir)/applications
desktop_DATA = gpredict.desktop

EXTRA_DIST = $(desktop_DATA)

UPDATE_DESKTOP = \
	if which update-desktop-database>/dev/null 2>&1 ; then \
		update-desktop-database; \
	fi

install-data-hook:
if UPDATE_CACHES
	$(UPDATE_DESKTOP)
else
	@true
endif

uninstall-hook:
if UPDATE_CACHES
	$(UPDATE_DESKTOP)
else
	@true
endif
