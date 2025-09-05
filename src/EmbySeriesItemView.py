from twisted.internet import threads
from Components.Label import Label

from .EmbyItemView import EmbyItemView
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyRestClient import EmbyApiClient
from .EmbyEpisodeItemView import EmbyEpisodeItemView
from .EmbyItemViewBase import EXIT_RESULT_EPISODE, EXIT_RESULT_SERIES
from .EmbySeasonsBar import EmbySeasonsBar
from .HelperFunctions import insert_at_position
from . import _


class EmbySeriesItemView(EmbyItemView):
	skin = ["""<screen name="EmbySeriesItemView" position="fill">
					<!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-3" scaleFlags="moveRightTop"/>
					<widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="infoline" position="60,160" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="60,230" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="f_buttons" position="60,440" size="924,65" font="Regular;32" transparent="1"/>
					<widget name="seasons_list" position="50,560" size="5*200,60" itemWidth="200" font="Regular;28" transparent="1"/>
					<widget name="episodes_list" position="40,630" size="e-80,438" iconWidth="407" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="cast_header" position="40,1078" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_cast" position="40,1128" size="e-80,426" iconWidth="205" iconHeight="310" font="Regular;19" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="chapters_header" position="40,1584" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_chapters" position="40,1644" size="e-80,310" iconWidth="395" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" transparent="1"/>
					<widget name="header_similar" position="40,1994" size="1100,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_similar" position="40,2054" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
				</screen>"""]

	def __init__(self, session, item, backdrop=None, logo=None):
		EmbyItemView.__init__(self, session, item, backdrop, logo)
		self.series_id = self.item_id
		self.episodes = []
		self["subtitle"] = Label()
		self["seasons_list"] = EmbySeasonsBar()
		self["episodes_list"] = EmbyList(type="episodes")
		self.episodes_controller = EmbyListController(self["episodes_list"], self["seasons_list"])
		self.lists = insert_at_position(self.lists, "episodes_list", self.episodes_controller, 0)
		self["header_similar"] = Label(_("Similar"))
		self["list_similar"] = EmbyList()
		self.lists["list_similar"] = EmbyListController(self["list_similar"], self["header_similar"])
		self["episodes_list"].onSelectionChanged.append(self.onEpisodeSelectionChanged)

	def onEpisodeSelectionChanged(self, widget=None, item_id=None):
		season_number_index = self["episodes_list"].selectedItem.get("ParentIndexNumber", 0) - 1
		if season_number_index > -1:
			self["seasons_list"].instance.moveSelectionTo(season_number_index)
			self["seasons_list"].updateInfo()

	def getEpisodes(self):
		seasons = EmbyApiClient.getSeasonsForSeries(self.series_id)
		list = []
		if seasons:
			i = 0
			for season in seasons:
				list.append((i, season, "%s %d" % (_("Season"), season.get("IndexNumber")), None, "0", True))
				i += 1
			self["seasons_list"].setList(list)
		self.episodes = EmbyApiClient.getEpisodesForSeries(self.series_id)
		list = []
		if self.episodes:
			i = 0
			for ep in self.episodes:
				if ep.get("ParentIndexNumber", 0) == 0:
					continue
				played_perc = ep.get("UserData", {}).get("PlayedPercentage", "0")
				title = f"S{ep.get("ParentIndexNumber", 0)}:E{ep.get("IndexNumber", 0)} - {" ".join(ep.get("Name", "").splitlines())}"
				list.append((i, ep, title, None, played_perc, True))
				i += 1
			self["episodes_list"].loadData(list)
			self.availableWidgets.insert(1, "episodes_list")
			self.lists["episodes_list"].visible(True).enableSelection(self.selected_widget == "episodes_list")

	def infoRetrieveInject(self, item):
		threads.deferToThread(self.getEpisodes)

	def loadExtraItems(self, itemObj):
		item_id = itemObj.get("Id")
		extras = EmbyApiClient.getExtrasForItem(item_id)
		list = []
		if extras:
			i = 0
			for item in extras:
				list.append((i, item, item.get('Name'), None, "0", True))
				i += 1
			self["list_extras"].loadData(list)
		if len(list) > 0:
			self.availableWidgets.append("list_extras")
			self.lists["list_extras"].visible(True)
		else:
			self.lists["list_extras"].visible(False)

		similar = EmbyApiClient.getSimilarForItem(item_id)
		list = []
		if similar:
			i = 0
			for item in similar:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list_similar"].loadData(list)
		if len(list) > 0:
			self.availableWidgets.append("list_similar")
			self.lists["list_similar"].visible(True)
		else:
			self.lists["list_similar"].visible(False)

	def injectAfterLoad(self, item):
		EmbyItemView.injectAfterLoad(self, item)
		threads.deferToThread(self.loadExtraItems, item)

	def onPlayerClosedResult(self):
		self.exitResult = EXIT_RESULT_SERIES

	def processItem(self):
		EmbyItemView.processItem(self)
		if self.selected_widget == "episodes_list":
			selected_item = self["episodes_list"].selectedItem
			self.session.openWithCallback(self.exitCallback, EmbyEpisodeItemView, selected_item, self.backdrop, self.logo)
		elif self.selected_widget == "list_similar":
			selected_item = self["list_similar"].selectedItem
			from .EmbySeriesItemView import EmbySeriesItemView as SeriesView
			self.session.openWithCallback(self.exitCallback, SeriesView, selected_item)
		elif self.selected_widget == "seasons_list":
			selected_item = self["seasons_list"].selectedItem
			index = next((i for i, ep in enumerate(self.episodes) if ep.get("ParentIndexNumber", 0) == selected_item[1].get("IndexNumber", 0)), -1)
			if index > -1:
				self["episodes_list"].instance.moveSelectionTo(index)
				self.selected_widget = "episodes_list"
				self.lists[self.selected_widget].enableSelection(True)
				self["seasons_list"].enableSelection(False)

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		if result == EXIT_RESULT_EPISODE:
			self.onPlayerClosedResult()
			threads.deferToThread(self.getEpisodes)
