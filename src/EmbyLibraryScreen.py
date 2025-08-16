from twisted.internet import threads
from enigma import eServiceReference
from Screens.Screen import Screen
from Screens.InfoBar import InfoBar
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap

from .EmbyGridList import EmbyGridList
from .EmbyRestClient import EmbyApiClient
from .EmbyPlayer import EmbyPlayer
from .EmbyMovieItemView import EmbyMovieItemView
from .EmbyEpisodeItemView import EmbyEpisodeItemView
from .EmbyBoxSetItemView import EmbyBoxSetItemView
from .EmbySeriesItemView import EmbySeriesItemView


class E2EmbyLibrary(Screen):
	skin = ["""<screen name="E2EmbyLibrary" position="fill">
					<widget name="list" position="40,0" size="e-80,e" iconWidth="173" iconHeight="260" spacing="10" scrollbarMode="showNever" transparent="1" />
				</screen>"""]  # noqa: E124

	def __init__(self, session, library_id):
		Screen.__init__(self, session)
		self.library_id = library_id
		self.boxsets = []
		self.movies = []
		self.setTitle(_("Emby Library"))
		self["list"] = EmbyGridList()
		self.onShown.append(self.__onShown)

		self["actions"] = ActionMap(["E2EmbyActions",],
			{
				"cancel": self.close,  # KEY_RED / KEY_EXIT
				# "save": self.addProvider,  # KEY_GREEN
				"ok": self.processItem,
				# "yellow": self.keyYellow,
				# "blue": self.clearData,
			}, -1)

	def __onShown(self):
		threads.deferToThread(self.loadItems)

	def processItem(self):
		selected_item = self["list"].getCurrentItem()
		item_type = selected_item.get("Type")
		embyScreenClass = EmbyMovieItemView
		if item_type == "Episode":
			embyScreenClass = EmbyEpisodeItemView
		elif item_type == "BoxSet":
			embyScreenClass = EmbyBoxSetItemView
		elif item_type == "Series":
			embyScreenClass = EmbySeriesItemView
		self.session.open(embyScreenClass, selected_item)

	def loadItems(self):
		items = EmbyApiClient.getItemsFromLibrary(self.library_id)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list"].loadData(list)
