from os.path import join
from twisted.internet import threads
from PIL import Image

from enigma import eServiceReference, eTimer
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.config import config
from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.InfoBar import InfoBar
from Screens.Screen import Screen

from .EmbyGridList import EmbyGridList
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyRestClient import EmbyApiClient
from .EmbyInfoLine import EmbyInfoLine
from .EmbyMovieItemView import EmbyMovieItemView
from .EmbyEpisodeItemView import EmbyEpisodeItemView
from .EmbyBoxSetItemView import EmbyBoxSetItemView
from .EmbySeriesItemView import EmbySeriesItemView
from .EmbyLibraryHeaderButtons import EmbyLibraryHeaderButtons
from .EmbyLibraryCharacterBar import EmbyLibraryCharacterBar
from .EmbyNotification import NotificationalScreen
from .Variables import plugin_dir, PAGERSUPPORT
from . import _


MODE_RECOMMENDATIONS = 0
MODE_LIST = 1
MODE_FAVORITES = 2


class E2EmbyLibrary(NotificationalScreen):
	pager = """<widget addon="Pager" connection="list" position="90,145+e-220+10" size="e-20-90,25" transparent="1" backgroundColor="background" zPosition="40" />"""
	skin = [f"""<screen name="E2EmbyLibrary" position="fill">
					<widget name="header" position="center,30" size="700,50" font="Bold;32" transparent="1" alphaBlend="1"/>
					<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="charbar" position="40,130" size="40,e-130-70" scrollbarMode="showNever" itemHeight="40" font="Regular;20" transparent="1" />
					<widget name="list" position="90,130" size="e-20-90,e-130-70" scrollbarMode="showOnDemand" iconWidth="225" iconHeight="315" font="Regular;22" transparent="1" />
					{(pager if PAGERSUPPORT else "")}
					<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-3" scaleFlags="moveRightTop"/>
					<widget name="title_logo" position="60,140" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="subtitle" position="60,235" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
					<widget name="infoline" position="60,240" size="e-120,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="60,310" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="list_watching_header" position="55,570" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_watching" position="40,620" size="e-80,268" iconWidth="338" iconHeight="192" scrollbarMode="showNever" iconType="Thumb" transparent="1" />
					<widget name="list_recent_added_header" position="55,928" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recent_added" position="40,978" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_0" position="55,1286" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_0" position="40,1336" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_1" position="55,1644" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_1" position="40,1694" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_2" position="55,2002" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_2" position="40,2052" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_3" position="55,2360" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_3" position="40,2410" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_4" position="55,2718" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_4" position="40,2768" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
					<widget name="list_recommend_header_5" position="55,3076" size="1400,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1" noWrap="1"/>
					<widget name="list_recommend_5" position="40,3126" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1" />
				</screen>"""]  # noqa: E101

	def __init__(self, session, library):
		NotificationalScreen.__init__(self, session)
		self.exitResult = 0
		self.library = library
		self.library_id = int(library.get("Id", "0"))
		self.type = library.get("CollectionType")
		self.is_init = False
		self.selected_widget = None
		self.last_selected_widget = None
		self.last_item_id = None
		self.backdrop_pix = None
		self.logo_pix = None
		self.mode = MODE_RECOMMENDATIONS
		self.plot_posy_orig = 310
		self.plot_height_orig = 168
		self.plot_width_orig = 924
		self.top_pos = 570
		self.setTitle(_("Emby Library"))
		self.sel_timer = eTimer()
		self.sel_timer.callback.append(self.trigger_sel_changed_event)
		self.mask_alpha = Image.open(join(plugin_dir, "mask_l.png")).convert("RGBA").split()[3]
		if self.mask_alpha.mode != "L":
			self.mask_alpha = self.mask_alpha.convert("L")
		self.list_data = []
		self.available_widgets = []
		self["header"] = EmbyLibraryHeaderButtons(self)
		self["charbar"] = EmbyLibraryCharacterBar()
		self["list"] = EmbyGridList()
		self["title_logo"] = Pixmap()
		self["title"] = Label()
		self["subtitle"] = Label()
		self["infoline"] = EmbyInfoLine(self)
		self["plot"] = Label()
		self["backdrop"] = Pixmap()
		# self["backdrop_full"] = Pixmap()
		self["list_watching_header"] = Label(_("Continue watching"))
		self["list_watching"] = EmbyList(type="item_fit")
		self["list_recent_added_header"] = Label(_("Recently added"))
		self["list_recent_added"] = EmbyList()
		self["list_recommend_header_0"] = Label("")
		self["list_recommend_0"] = EmbyList()
		self["list_recommend_header_1"] = Label("")
		self["list_recommend_1"] = EmbyList()
		self["list_recommend_header_2"] = Label("")
		self["list_recommend_2"] = EmbyList()
		self["list_recommend_header_3"] = Label("")
		self["list_recommend_3"] = EmbyList()
		self["list_recommend_header_4"] = Label("")
		self["list_recommend_4"] = EmbyList()
		self["list_recommend_header_5"] = Label("")
		self["list_recommend_5"] = EmbyList()
		self.lists = {}
		self.lists["list_watching"] = EmbyListController(self["list_watching"], self["list_watching_header"])
		self.lists["list_recent_added"] = EmbyListController(self["list_recent_added"], self["list_recent_added_header"])
		self.lists["list_recommend_0"] = EmbyListController(self["list_recommend_0"], self["list_recommend_header_0"])
		self.lists["list_recommend_1"] = EmbyListController(self["list_recommend_1"], self["list_recommend_header_1"])
		self.lists["list_recommend_2"] = EmbyListController(self["list_recommend_2"], self["list_recommend_header_2"])
		self.lists["list_recommend_3"] = EmbyListController(self["list_recommend_3"], self["list_recommend_header_3"])
		self.lists["list_recommend_4"] = EmbyListController(self["list_recommend_4"], self["list_recommend_header_4"])
		self.lists["list_recommend_5"] = EmbyListController(self["list_recommend_5"], self["list_recommend_header_5"])
		self["list_watching"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recent_added"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_0"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_1"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_2"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_3"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_4"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recommend_5"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self.onShown.append(self.__onShown)
		self.onLayoutFinish.append(self.__onLayoutFinished)

		self["actions"] = ActionMap(["E2EmbyActions",],
									{
			"cancel": self.__closeScreen,  # KEY_RED / KEY_EXIT
			"ok": self.processItem,
		}, -1)

		self["nav_actions"] = ActionMap(["NavigationActions", "MenuActions"],
										{
			"up": self.up,
			"down": self.down,
			"left": self.left,
			"right": self.right,
			"pageUp": self.pageUp,
			"pageDown": self.pageDown,
			"menu": self.menu
		}, -2)

	def __closeScreen(self):
		self.close(self.exitResult)

	def __onShown(self):
		if not self.is_init:
			self.is_init = True
			self["header"].setItem(self.library)
			threads.deferToThread(self.loadSuggestedTabItems)
			if self.type != "boxsets":
				self["list"].hide()
				self["charbar"].hide()
				self["charbar"].enableSelection(False)
				self["list"].toggleSelection(False)
			else:
				self.mode = MODE_LIST
				threads.deferToThread(self.loadItems)
				self.toggleSuggestionSectionVisibility(False)
				self.toggleItemsSectionVisibility(True)
				self.selected_widget = "list"

	def __onLayoutFinished(self):
		plot = self["plot"]
		plot_pos = plot.instance.position()
		plot_size = plot.instance.size()
		self.plot_posy_orig = plot_pos.y()
		self.plot_height_orig = plot_size.height()
		self.plot_width_orig = plot_size.width()
		self.top_pos = self["list_watching_header"].instance.position().y()
		for item in self.lists:
			self.lists[item].visible(False)

	def onSelectedIndexChanged(self, widget=None, item_id=None):
		sel_widget = self.selected_widget if self.selected_widget != "header" else self.available_widgets[0]
		if not sel_widget or isinstance(self[sel_widget].selectedItem, tuple):
			return
		if self.last_item_id and self.last_item_id == self[sel_widget].selectedItem.get("Id"):
			return
		self.last_item_id = self[sel_widget].selectedItem.get("Id")

		if not item_id:
			item_id = self[sel_widget].selectedItem.get("Id")

		self.sel_timer.stop()
		self.sel_timer.start(config.plugins.e2embyclient.changedelay.value, True)

	def trigger_sel_changed_event(self):
		sel_widget = self.selected_widget if self.selected_widget != "header" else self.available_widgets[0]
		threads.deferToThread(self.loadSelectedItemDetails, self[sel_widget].selectedItem, self[sel_widget])

	def pageUp(self):
		self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.prevPage)

	def pageDown(self):
		self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.nextPage)

	def menu(self):
		if self.type == "boxsets":
			return
		if self.selected_widget == "charbar":
			self["charbar"].enableSelection(False)
		else:
			if hasattr(self[self.selected_widget], "enableSelection"):
				self[self.selected_widget].enableSelection(False)
			else:
				self[self.selected_widget].toggleSelection(False)
		self.last_selected_widget = self.selected_widget
		self.selected_widget = "header"
		self[self.selected_widget].setFocused(True)

	def left(self):
		if self.selected_widget is None:
			return

		if self.selected_widget == "charbar" and self.mode in [MODE_LIST, MODE_FAVORITES]:
			return
		if self.mode in [MODE_LIST, MODE_FAVORITES] and self.selected_widget == "list" and self["list"].getIsAtFirstColumn():
			self.selected_widget = "charbar"
			self["list"].toggleSelection(False)
			self["charbar"].enableSelection(True)
			return

		if self.selected_widget == "header":
			self[self.selected_widget].movePrevious()
		else:
			if self[self.selected_widget].selectedIndex > 0:
				self.backdrop_pix = None
				self["backdrop"].setPixmap(None)
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveLeft)

	def right(self):
		if self.selected_widget is None:
			return

		if self.selected_widget == "charbar":
			self.selected_widget = "list"
			self["list"].toggleSelection(True)
			self["charbar"].instance.moveSelectionTo(0)
			self["charbar"].enableSelection(False)
			return

		if self.selected_widget == "header":
			self[self.selected_widget].moveNext()
		else:
			if self[self.selected_widget].selectedIndex < len(self[self.selected_widget].data) - 1:
				self.backdrop_pix = None
				self["backdrop"].setPixmap(None)
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveRight)

	def up(self):
		if self.selected_widget == "header":
			return

		current_widget_index = self.available_widgets.index(self.selected_widget) if self.selected_widget in self.available_widgets else -1
		if (self.selected_widget == "list" and self["list"].getIsAtFirstRow()) or current_widget_index == 0:
			if self.type != "boxsets":
				self[self.selected_widget].toggleSelection(False)
				self.last_selected_widget = self.selected_widget
				self.selected_widget = "header"
				self[self.selected_widget].setFocused(True)
		else:
			if self.selected_widget == "list":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveUp)
			elif self.selected_widget == "charbar":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveUp)
			else:
				self.last_item_id = None
				current_widget_index = self.available_widgets.index(self.selected_widget)
				y = self.top_pos

				prevWidgetName = self.available_widgets[current_widget_index - 1]
				prevItem = self.lists[prevWidgetName]
				prevItem.move(40, y).visible(True).enableSelection(True)
				y += prevItem.getHeight() + 40
				self.selected_widget = prevWidgetName

				for item in self.available_widgets[current_widget_index:]:
					self.lists[item].move(40, y).enableSelection(False)
					y += self.lists[item].getHeight() + 40

				self.backdrop_pix = None
				self["backdrop"].setPixmap(None)

				self.onSelectedIndexChanged()

	def down(self):
		current_widget_index = self.available_widgets.index(self.selected_widget) if self.selected_widget in self.available_widgets else -1
		if self.selected_widget == "header":
			self[self.selected_widget].setFocused(False)
			self[self.selected_widget].setSelectedIndex(self.mode)
			self.selected_widget = self.available_widgets[0] if self.mode == MODE_RECOMMENDATIONS else "list"
			self[self.selected_widget].toggleSelection(True)
			self.last_selected_widget = self.selected_widget
		else:
			if self.selected_widget == "list":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveDown)
			elif self.selected_widget == "charbar":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveDown)
			else:
				if current_widget_index == len(self.available_widgets) - 1:
					return
				self.last_item_id = None
				safe_index = min(current_widget_index + 1, len(self.available_widgets))
				for item in self.available_widgets[:safe_index]:
					self.lists[item].visible(False).enableSelection(False)

				y = self.top_pos
				selEnabled = True
				for item in self.available_widgets[safe_index:]:
					self.lists[item].move(40, y).enableSelection(selEnabled)
					y += self.lists[item].getHeight() + 40
					if selEnabled:
						self.selected_widget = item
					selEnabled = False

				self.backdrop_pix = None
				self["backdrop"].setPixmap(None)
				self.onSelectedIndexChanged()

	def toggleItemsSectionVisibility(self, visible):
		if visible:
			self["list"].show()
			self["charbar"].show()
		else:
			self["list"].hide()
			self["charbar"].hide()

	def toggleSuggestionSectionVisibility(self, visible):
		if visible:
			self["title_logo"].show()
			self["title"].show()
			self["subtitle"].show()
			self["infoline"].show()
			self["plot"].show()
			self["backdrop"].show()
			self.lists["list_watching"].visible("list_watching" in self.available_widgets)
			self.lists["list_recent_added"].visible("list_recent_added" in self.available_widgets)
			self.lists["list_recommend_0"].visible("list_recommend_0" in self.available_widgets)
			self.lists["list_recommend_1"].visible("list_recommend_1" in self.available_widgets)
			self.lists["list_recommend_2"].visible("list_recommend_2" in self.available_widgets)
			self.lists["list_recommend_3"].visible("list_recommend_3" in self.available_widgets)
			self.lists["list_recommend_4"].visible("list_recommend_4" in self.available_widgets)
			self.lists["list_recommend_5"].visible("list_recommend_5" in self.available_widgets)
			self.setWidgetsPosition(True)
		else:
			self["title_logo"].hide()
			self["title"].hide()
			self["subtitle"].hide()
			self["infoline"].hide()
			self["plot"].hide()
			self["backdrop"].hide()
			self.lists["list_watching"].visible(False)
			self.lists["list_recent_added"].visible(False)
			self.lists["list_recommend_0"].visible(False)
			self.lists["list_recommend_1"].visible(False)
			self.lists["list_recommend_2"].visible(False)
			self.lists["list_recommend_3"].visible(False)
			self.lists["list_recommend_4"].visible(False)
			self.lists["list_recommend_5"].visible(False)

	def processItem(self):
		if self.selected_widget == "header":
			selected_item = self[self.selected_widget].getSelectedButton()
			command = selected_item[2]
			if command == "recommend":
				self.mode = MODE_RECOMMENDATIONS
				self.toggleSuggestionSectionVisibility(True)
				self.toggleItemsSectionVisibility(False)
			elif command == "list":
				self.mode = MODE_LIST
				threads.deferToThread(self.loadItems)
				self.toggleSuggestionSectionVisibility(False)
				self.toggleItemsSectionVisibility(True)
			elif command == "favlist":
				self.mode = MODE_FAVORITES
				threads.deferToThread(self.loadFavItems)
				self.toggleSuggestionSectionVisibility(False)
				self.toggleItemsSectionVisibility(True)
		elif self.selected_widget == "charbar":
			char = self[self.selected_widget].selectedItem
			index = 0
			if char != "#":
				index = next((i for i, x in enumerate(self.list_data)
							if x[1].get("Name")[0].upper() == char), -1)
			self.selected_widget = "list"
			self[self.selected_widget].toggleSelection(True)
			self[self.selected_widget].instance.moveSelectionTo(index)
			self["charbar"].enableSelection(False)
		else:
			selected_item = self[self.selected_widget].getCurrentItem()
			item_type = selected_item.get("Type")
			embyScreenClass = EmbyMovieItemView
			if item_type == "Episode":
				embyScreenClass = EmbyEpisodeItemView
			elif item_type == "BoxSet":
				embyScreenClass = EmbyBoxSetItemView
			elif item_type == "Series":
				embyScreenClass = EmbySeriesItemView
			self.session.openWithCallback(self.exitCallback, embyScreenClass,
										selected_item, self.mode == MODE_RECOMMENDATIONS and self.backdrop_pix, self.mode != MODE_LIST and self.logo_pix)

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		self.exitResult = result
		if result != 0:
			threads.deferToThread(self.loadSuggestedTabItems)
			if self.mode == MODE_LIST:
				threads.deferToThread(self.loadItems)
			elif self.mode == MODE_FAVORITES:
				threads.deferToThread(self.loadFavItems)

	def loadItems(self):
		if self.list_data:
			self["list"].loadData([])
			self.list_data = []
			self["charbar"].setList([])
			self.onSelectedIndexChanged()
		items = EmbyApiClient.getItemsFromLibrary(self.library_id, self.type)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list"].loadData(list)
		self.list_data = list
		self["charbar"].setList(list)
		self.onSelectedIndexChanged()

	def loadFavItems(self):
		if self.list_data:
			self["list"].loadData([])
			self.list_data = []
			self["charbar"].setList([])
			self.onSelectedIndexChanged()
		items = EmbyApiClient.getFavItemsFromLibrary(self.library_id, self.type)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list"].loadData(list)
		self.list_data = list
		self["charbar"].setList(list)
		self.onSelectedIndexChanged()

	def loadSuggestionTabbleItems(self):
		if self.lists is None:
			return
		self.available_widgets = []
		items = EmbyApiClient.getResumableItemsForLibrary(self.library_id, self.type)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list_watching"].loadData(list)
			is_available = len(list) > 0
			if is_available:
				self.available_widgets.append("list_watching")
				if not self.selected_widget:
					self.selected_widget = self.available_widgets[0]
					self.lists[self.selected_widget].enableSelection(True)
			else:
				self.available_widgets.remove("list_watching")
			is_visible = is_available and self.mode == MODE_RECOMMENDATIONS and self.selected_widget == "list_watching"
			self.lists["list_watching"].visible(is_visible).enableSelection(is_visible)

		items = EmbyApiClient.getRecentlyAddedItemsForLibrary(self.library_id)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list_recent_added"].loadData(list)
			is_available = len(list) > 0
			if is_available:
				self.available_widgets.append("list_recent_added")
				if not self.selected_widget:
					self.selected_widget = self.available_widgets[0]
					self.lists[self.selected_widget].enableSelection(True)
			else:
				self.available_widgets.remove("list_recent_added")

			is_visible = is_available and self.mode == MODE_RECOMMENDATIONS
			self.lists["list_recent_added"].visible(is_visible and (self.selected_widget in ["list_recent_added", "list_watching"])).enableSelection(is_visible and (self.selected_widget == "list_recent_added"))
		if self.type == "movies":
			categories = EmbyApiClient.getRecommendedMoviesForLibrary(self.library_id)
			ki = 0
			for category in categories:
				widget_name = f"list_recommend_{ki}"
				recomm_type = category.get("RecommendationType")
				base_item = category.get("BaselineItemName", "")
				h_text = ""
				if recomm_type == "SimilarToRecentlyPlayed":
					h_text = "%s %s" % (_('Because you recently watched'), base_item)
				elif recomm_type == "SimilarToLikedItem":
					h_text = "%s %s" % (_('Because you liked'), base_item)
				elif recomm_type == "HasDirectorFromRecentlyPlayed":
					h_text = "%s %s" % (_('From director'), base_item)
				elif recomm_type == "HasActorFromRecentlyPlayed":
					h_text = "%s %s" % (_('With actor'), base_item)
				self.lists[widget_name].setHeaderText(h_text)
				ki += 1
				items = category.get("Items")
				list = []
				if items:
					i = 0
					for item in items:
						played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
						list.append((i, item, item.get('Name'), None, played_perc, True))
						i += 1
					self[widget_name].loadData(list)
					is_available = len(list) > 0
					if is_available:
						self.available_widgets.append(widget_name)
						if not self.selected_widget:
							self.selected_widget = self.available_widgets[0]
							self.lists[self.selected_widget].enableSelection(True)
					else:
						self.available_widgets.remove(widget_name)

					is_visible = is_available and self.mode == MODE_RECOMMENDATIONS and self.selected_widget == widget_name
					self.lists[widget_name].visible(is_visible).enableSelection(is_visible)
		self.onSelectedIndexChanged()

	def setWidgetsPosition(self, result):
		sel_widget = self.selected_widget
		if result:
			sel_widget = self.available_widgets[0]

		current_widget_index = self.available_widgets.index(sel_widget) if sel_widget in self.available_widgets else -1
		if current_widget_index == -1:
			return

		for item in self.available_widgets[:current_widget_index]:
			self.lists[item].visible(False).enableSelection(False)

		y = self.top_pos
		for widget in self.available_widgets[current_widget_index:]:
			h = self.lists[widget].getHeight()
			x = 40
			self.lists[widget].move(x, y).visible(self.mode == MODE_RECOMMENDATIONS)
			y += h + 40
		self.onSelectedIndexChanged()

	def loadSuggestedTabItems(self):
		threads.deferToThread(self.loadSuggestionTabbleItems).addCallback(self.setWidgetsPosition)

	def loadSelectedItemDetails(self, item, widget):
		if not self.is_init:
			return

		orig_item_id = item.get("Id")
		item_id = orig_item_id

		if orig_item_id != self.last_item_id:
			return

		parent_b_item_id = item.get("ParentLogoItemId")
		if parent_b_item_id:
			item_id = parent_b_item_id

		logo_tag = item.get("ImageTags", {}).get("Logo", None)
		parent_logo_tag = item.get("ParentLogoImageTag", None)
		if parent_logo_tag:
			logo_tag = parent_logo_tag

		itemType = item.get("Type", None)

		if logo_tag:
			logo_widget_size = self["title_logo"].instance.size()
			max_w = logo_widget_size.width()
			max_h = logo_widget_size.height()
			logo_pix = EmbyApiClient.getItemImage(
				item_id=item_id, logo_tag=logo_tag, max_width=max_w, max_height=max_h, image_type="Logo", format="png")
			self.logo_pix = logo_pix
			if logo_pix:
				self["title_logo"].setPixmap(self.logo_pix)
				self["title"].text = ""
			else:
				if itemType == "Episode":
					self["title"].text = " ".join(
						item.get("SeriesName", "").splitlines())
				else:
					self["title"].text = " ".join(
						item.get("Name", "").splitlines())
				self["title_logo"].setPixmap(None)
		else:
			if itemType == "Episode":
				self["title"].text = " ".join(
					item.get("SeriesName", "").splitlines())
			else:
				self["title"].text = " ".join(
					item.get("Name", "").splitlines())
			self["title_logo"].setPixmap(None)

		if itemType == "Episode":
			sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
			self["subtitle"].text = sub_title
			subtitlesize = self["subtitle"].getSize()
			plotpos = self["plot"].instance.position()
			self["plot"].move(
				plotpos.x(), self.plot_posy_orig + subtitlesize[1])
			self["plot"].resize(self.plot_width_orig,
								self.plot_height_orig - subtitlesize[1] - 20)
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(
				infolinepos.x(), self.plot_posy_orig + subtitlesize[1] - infolinesize[1] - 10)
		else:
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig)
			self["plot"].resize(self.plot_width_orig, self.plot_height_orig)
			self["subtitle"].text = ""
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(
				infolinepos.x(), self.plot_posy_orig - infolinesize[1] - 10)

		self["infoline"].updateInfo(item)

		self["plot"].text = item.get("Overview", "")

		backdrop_image_tags = item.get("BackdropImageTags")
		parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
		if parent_backdrop_image_tags:
			backdrop_image_tags = parent_backdrop_image_tags

		if not backdrop_image_tags or len(backdrop_image_tags) == 0:
			self["backdrop"].setPixmap(None)
			self.backdrop_pix = None
			return

		icon_img = backdrop_image_tags[0]
		parent_b_item_id = item.get("ParentBackdropItemId")
		if parent_b_item_id:
			item_id = parent_b_item_id
		if orig_item_id != self.last_item_id:
			return
		threads.deferToThread(self.downloadCover, item_id, icon_img, orig_item_id)

	def downloadCover(self, item_id, icon_img, orig_item_id):
		try:
			backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1280, image_type="Backdrop", alpha_channel=self.mask_alpha)
			if orig_item_id != self.last_item_id:
				return
			if backdrop_pix:
				self["backdrop"].setPixmap(backdrop_pix)
				self.backdrop_pix = backdrop_pix
			else:
				self["backdrop"].setPixmap(None)
				self.backdrop_pix = None
		except:
			pass
