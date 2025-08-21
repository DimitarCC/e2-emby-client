from twisted.internet import threads
from Components.Label import Label

from .EmbyItemView import EmbyItemView
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyRestClient import EmbyApiClient
from .EmbyEpisodeItemView import EmbyEpisodeItemView
from .EmbyItemViewBase import EXIT_RESULT_EPISODE, EXIT_RESULT_SERIES
from .HelperFunctions import insert_at_position
from . import _


class EmbySeriesItemView(EmbyItemView):
    skin = ["""<screen name="EmbySeriesItemView" position="fill">
                    <!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
                    <widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget name="backdrop" position="e-1280,0" size="1280,720" alphatest="blend" zPosition="-3"/>
                    <widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
                    <widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
                    <widget name="infoline" position="60,160" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
                    <widget name="plot" position="60,230" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
                    <widget name="f_buttons" position="60,440" size="924,65" font="Regular;32" transparent="1"/>
                    <!--<widget name="seasons_list" position="40,630" size="900,60" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>-->
                    <widget name="episodes_list" position="40,630" size="e-80,408" iconWidth="407" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
                    <widget name="cast_header" position="40,1186" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
                    <widget name="list_cast" position="40,1250" size="e-80,426" iconWidth="180" iconHeight="270" font="Regular;20" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
                    <widget name="chapters_header" position="40,1716" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
                    <widget name="list_chapters" position="40,1800" size="e-80,426" iconWidth="407" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" orientation="orHorizontal" transparent="1"/>
                </screen>"""]

    def __init__(self, session, item, backdrop=None):
        EmbyItemView.__init__(self, session, item, backdrop)
        self.series_id = self.item_id
        self["subtitle"] = Label()
        self["seasons_list"] = EmbyList()
        self["episodes_list"] = EmbyList(type="episodes")
        self.episodes_controller = EmbyListController(
            self["episodes_list"], None)
        self.lists = insert_at_position(
            self.lists, "episodes_list", self.episodes_controller, 0)

        # self["actions"] = ActionMap(["E2EmbyActions",],
        #     {
        #         "cancel": self.close,  # KEY_RED / KEY_EXIT
        #         # "save": self.addProvider,  # KEY_GREEN
        #         "ok": self.processItem,
        #         # "yellow": self.keyYellow,
        #         # "blue": self.clearData,
        #     }, -1)
    def getEpisodes(self):
        episodes = EmbyApiClient.getEpisodesForSeries(self.series_id)
        list = []
        if episodes:
            i = 0
            for ep in episodes:
                if ep.get("ParentIndexNumber", 0) == 0:
                    continue
                played_perc = ep.get("UserData", {}).get(
                    "PlayedPercentage", "0")
                title = f"S{ep.get("ParentIndexNumber", 0)}:E{ep.get("IndexNumber", 0)} - {" ".join(ep.get("Name", "").splitlines())}"
                list.append((i, ep, title, None, played_perc, True))
                i += 1
            self["episodes_list"].loadData(list)
            self.availableWidgets.insert(1, "episodes_list")
            self.lists["episodes_list"].visible(True).enableSelection(
                self.selected_widget == "episodes_list")

    def infoRetrieveInject(self, item):
        # sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
        # self["subtitle"].text = sub_title
        threads.deferToThread(self.getEpisodes)

    def onPlayerClosedResult(self):
        self.exitResult = EXIT_RESULT_SERIES

    def processItem(self):
        EmbyItemView.processItem(self)
        if self.selected_widget == "episodes_list":
            selected_item = self["episodes_list"].selectedItem
            self.session.openWithCallback(
                self.exitCallback, EmbyEpisodeItemView, selected_item, self.backdrop)

    def exitCallback(self, *result):
        if not len(result):
            return
        result = result[0]
        if result == EXIT_RESULT_EPISODE:
            self.onPlayerClosedResult()
            threads.deferToThread(self.getEpisodes)
