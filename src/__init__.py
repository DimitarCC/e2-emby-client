#!/usr/bin/python
# -*- coding: utf-8 -*-
from gettext import bindtextdomain, dgettext, gettext

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS


PluginLanguageDomain = "e2embyclient"
PluginLanguagePath = "Extensions/E2EmbyClient/locale"


__version__ = "1.0"


def pluginlanguagedomain():
	return PluginLanguageDomain


def localeInit():
	bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
	if translated := dgettext(PluginLanguageDomain, txt):
		return translated
	else:
		print(f"[{PluginLanguageDomain}] fallback to default translation for {txt}")
		return gettext(txt)


localeInit()
language.addCallback(localeInit)
