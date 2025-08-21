from .EmbySetup import initConfig, EmbySetup
from Plugins.Plugin import PluginDescriptor
from os import makedirs
from .EmbyHome import E2EmbyHome
from . import _, PluginLanguageDomain
from . import EmbyRestClient

initConfig()

EmbyRestClient.set_agent()


def setup(session, **kwargs):
    session.open(EmbySetup)


def main(session, **kwargs):
    session.open(E2EmbyHome)


def startHome(menuid):
    if menuid != "mainmenu":
        return []
    return [(_("E2Emby"), main, "e2_emby_menu", 100)]


def sessionstart(reason, session, **kwargs):
    makedirs("/tmp/emby/", exist_ok=True)


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
