from .EmbySetup import initConfig, EmbySetup
from Plugins.Plugin import PluginDescriptor
from os import makedirs, path
from .EmbyHome import E2EmbyHome
from . import _, PluginLanguageDomain
from .Variables import EMBY_THUMB_CACHE_DIR
from Components.Harddisk import harddiskmanager
from Components.config import config, ConfigSelection

initConfig()


class MountChoices:
    def __init__(self):
        choices = self.getMountChoices()
        config.plugins.e2embyclient.thumbcache_loc = ConfigSelection(choices=choices, default=self.getMountDefault(choices))
        harddiskmanager.on_partition_list_change.append(MountChoices.__onPartitionChange)  # to update data location choices on mountpoint change

    @staticmethod
    def getMountChoices():
        choices = []
        for p in harddiskmanager.getMountedPartitions():
            if path.exists(p.mountpoint):
                d = path.normpath(p.mountpoint)
                if p.mountpoint != "/":
                    choices.append((d, f"{_('Persistent thumbnail cache in')} {p.mountpoint}"))
        choices.sort()
        choices.insert(0, ("/tmp", _("Temporary thumbnail cache")))
        choices.insert(0, ("off", _("off")))
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


def setup(session, **kwargs):
    session.open(EmbySetup)


def main(session, **kwargs):
    session.open(E2EmbyHome)


def startHome(menuid):
    if menuid != "mainmenu":
        return []
    return [(_("E2Emby"), main, "e2_emby_menu", 100)]


def sessionstart(reason, session, **kwargs):
    makedirs(f"/tmp{EMBY_THUMB_CACHE_DIR}", exist_ok=True)
    if config.plugins.e2embyclient.thumbcache_loc.value != "off":
        makedirs(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}", exist_ok=True)


def Plugins(path, **kwargs):
    try:
        result = [
            PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART,
                             fnc=sessionstart, needsRestart=False),
            PluginDescriptor(name=_("E2Emby"), description=_("A client for Emby server"),
                             where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=startHome),
            PluginDescriptor(name=_("E2Emby Client Setup"), description=_(
                "A client for Emby server setup"), where=PluginDescriptor.WHERE_PLUGINMENU, icon='plugin.png', fnc=setup)
        ]
        return result
    except ImportError:
        return PluginDescriptor()
