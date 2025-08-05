from . import _

import os
from sys import modules
from twisted.internet import threads
from Screens.Screen import Screen, ScreenSummary
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap

from .EmbyRestClient import EmbyApiClient
from .EmbyInfoLine import EmbyInfoLine
from .EmbyItemView import EmbyItemView

from PIL import Image

plugin_dir = os.path.dirname(modules[__name__].__file__)

class EmbyMovieItemView(EmbyItemView):
    skin = ["""<screen name="EmbyMovieItemView" position="fill">
                    <ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
                    <widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget name="backdrop" position="e-1280,0" size="1280,720" alphatest="blend" zPosition="-3"/>
                    <widget name="title_logo" position="60,140" size="924,80" alphatest="blend"/>
                    <widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
                    <widget name="infoline" position="60,240" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
                    <widget name="tagline" position="60,310" size="924,50" alphatest="blend" font="Bold;42" foregroundColor="yellow" transparent="1"/>
                    <widget name="plot" position="60,310" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
                </screen>"""]  # noqa: E124

    def __init__(self, session, item, backdrop=None):
        EmbyItemView.__init__(self, session, item, backdrop)
        self.setTitle(_("Emby") + item.get("Name"))

        self["tagline"] = Label()
        self["actions"] = ActionMap(["E2EmbyActions",],
            {
                "cancel": self.close,  # KEY_RED / KEY_EXIT
                # "save": self.addProvider,  # KEY_GREEN
                #"ok": self.processItem,
                # "yellow": self.keyYellow,
                # "blue": self.clearData,
            }, -1)  # noqa: E123
        

    def preLayoutFinished(self):
        plot_pos = self["plot"].instance.position()
        tagline_h = self["tagline"].instance.size().height()
        taglines = self.item.get("Taglines", [])
        if len(taglines) > 0:
            self["plot"].move(plot_pos.x(), plot_pos.y() + tagline_h + 35)

    def infoRetrieveInject(self, item):
        taglines = item.get("Taglines", [])
        if len(taglines) > 0:
            tagline = taglines[0]
            self["tagline"].text = tagline
        


        