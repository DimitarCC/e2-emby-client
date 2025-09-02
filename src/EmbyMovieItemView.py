from . import _

from Components.Label import Label

from .EmbyItemView import EmbyItemView
from .EmbyItemViewBase import EXIT_RESULT_MOVIE
from .EmbyList import EmbyList


class EmbyMovieItemView(EmbyItemView):
    skin = ["""<screen name="EmbyMovieItemView" position="fill">
                    <!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
                    <widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-10" scaleFlags="moveRightTop"/>
                    <widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
                    <widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
                    <widget name="infoline" position="60,160" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1"/>
                    <widget name="tagline" position="60,230" size="1400,50" alphatest="blend" font="Bold;42" foregroundColor="yellowsoft" transparent="1" shadowColor="black" shadowOffset="-1,-1"/>
                    <widget name="plot" position="60,230" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
                    <widget name="f_buttons" position="60,520" size="924,65" font="Regular;26" transparent="1"/>
                    <widget name="cast_header" position="40,630" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
                    <widget name="list_cast" position="40,700" size="e-80,426" iconWidth="180" iconHeight="270" font="Regular;20" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
                    <widget name="chapters_header" position="40,1166" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
                    <widget name="list_chapters" position="40,1230" size="e-80,426" iconWidth="395" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" orientation="orHorizontal" transparent="1"/>
               </screen>"""]

    def __init__(self, session, item, backdrop=None, logo=None):
        EmbyItemView.__init__(self, session, item, backdrop, logo)
        self.setTitle(_("Emby") + item.get("Name"))

        self["tagline"] = Label()
        self["header_parent_boxsets"] = Label(_("Included in"))
        self["list_parent_boxsets"] = EmbyList()

    def preLayoutFinished(self):
        plot_pos = self["plot"].instance.position()
        tagline_h = self["tagline"].instance.size().height()
        taglines = self.item.get("Taglines", [])
        if len(taglines) > 0:
            self["plot"].move(plot_pos.x(), plot_pos.y() + tagline_h + 15)
        EmbyItemView.preLayoutFinished(self)

    def onPlayerClosedResult(self):
        self.exitResult = EXIT_RESULT_MOVIE

    def infoRetrieveInject(self, item):
        taglines = item.get("Taglines", [])
        if len(taglines) > 0:
            tagline = taglines[0]
            self["tagline"].text = tagline
