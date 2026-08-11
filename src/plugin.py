from enigma import getDesktop, eTimer
from os import makedirs
from os.path import exists, normpath
from Components.config import config, ConfigSelection
from Components.Harddisk import harddiskmanager
from Plugins.Plugin import PluginDescriptor
from Tools.BoundFunction import boundFunction

from .EmbySetup import EmbySetup, initConfig
from .EmbyHome import E2EmbyHome
from .Variables import EMBY_THUMB_CACHE_DIR
from . import _

initConfig()

PROGRAM_NAME = _("Emby Player")
PROGRAM_DESCRIPTION = _("A client for Emby server")


class MountChoices:
	def __init__(self):
		choices = self.getMountChoices()
		config.plugins.e2embyclient.thumbcache_loc = ConfigSelection(choices=choices, default=self.getMountDefault(choices))
		harddiskmanager.on_partition_list_change.append(MountChoices.__onPartitionChange)  # to update data location choices on mountpoint change

	@staticmethod
	def getMountChoices():
		choices = []
		for p in harddiskmanager.getMountedPartitions():
			if exists(p.mountpoint):
				d = normpath(p.mountpoint)
				if p.mountpoint != "/":
					choices.append((d, "%s %s" % (_('Persistent thumbnail cache in'), p.mountpoint)))
		choices.sort()
		choices.insert(0, ("/tmp", _("Temporary thumbnail cache")))
		return choices

	@staticmethod
	def getMountDefault(choices):
		choices = {x[1]: x[0] for x in choices}
		default = "/tmp"  # choices.get("/media/hdd") or choices.get("/media/usb") or ""
		return default

	@staticmethod
	def __onPartitionChange(*args, **kwargs):
		choices = MountChoices.getMountChoices()
		config.plugins.e2embyclient.thumbcache_loc.setChoices(choices=choices, default=MountChoices.getMountDefault(choices))


MountChoices()


class _ServiceRestorer:
	# Navigation's own "tuner still releasing from a just-stopped stream" retry
	# only arms when the previous service reference still has "://" in it at
	# the moment playService() is called - which isn't the case here, since the
	# service has been sitting stopped for as long as the plugin was open. So
	# retry the restore ourselves a few times, mirroring Navigation's own
	# cadence/window, in case the tuner hasn't fully released yet.
	MAX_ATTEMPTS = 14
	RETRY_DELAY = 700  # ms

	def __init__(self, session, ref):
		self.session = session
		self.ref = ref
		self.attempts = 0
		self.timer = eTimer()
		self.timer.callback.append(self.__attempt)
		self.timer.start(300, True)

	def __attempt(self):
		if self.session.nav.getCurrentlyPlayingServiceReference() is not None:
			return
		self.attempts += 1
		self.session.nav.playService(self.ref)
		if self.attempts < self.MAX_ATTEMPTS:
			self.timer.start(self.RETRY_DELAY, True)


def restoreStoppedService(session, stopped_service_ref, *result):
	if stopped_service_ref is not None:
		_ServiceRestorer(session, stopped_service_ref)


def main(session, **kwargs):
	screenwidth = getDesktop(0).size().width()
	if screenwidth < 1920:
		from Screens.MessageBox import MessageBox
		session.open(MessageBox, _("E2EmbyClient works only with FHD (1920x1080) skins. Please load FHD skin."), MessageBox.TYPE_ERROR, simple=True, timeout=20)
		return
	if not config.plugins.e2embyclient.connectioncount.value:
		session.open(EmbySetup)
		return
	stopped_service_ref = None
	if config.plugins.e2embyclient.stop_playing_service_on_load.value:
		stopped_service_ref = session.nav.getCurrentServiceReferenceOriginal()
		if stopped_service_ref is not None:
			session.nav.stopService()
	session.openWithCallback(boundFunction(restoreStoppedService, session, stopped_service_ref), E2EmbyHome)


def startFromMainMenu(menuid):
	if menuid != "mainmenu":
		return []
	return [(_("Emby Player"), main, "e2_emby_menu", 100)]


def sessionstart(reason, session, **kwargs):
	makedirs(f"/tmp{EMBY_THUMB_CACHE_DIR}", exist_ok=True)
	if config.plugins.e2embyclient.thumbcache_loc.value != "off":
		makedirs(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}", exist_ok=True)


def Plugins(path, **kwargs):
	plugin = [
		PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart, needsRestart=False),
		PluginDescriptor(name=PROGRAM_NAME, description=PROGRAM_DESCRIPTION, where=PluginDescriptor.WHERE_PLUGINMENU, icon='plugin.png', fnc=main)
	]
	if config.plugins.e2embyclient.add_to_extensionmenu.value:
		plugin.append(PluginDescriptor(name=PROGRAM_NAME, description=PROGRAM_DESCRIPTION, where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=main))
	if config.plugins.e2embyclient.add_to_mainmenu.value:
		plugin.append(PluginDescriptor(name=PROGRAM_NAME, description=PROGRAM_DESCRIPTION, where=PluginDescriptor.WHERE_MENU, fnc=startFromMainMenu))

	return plugin
