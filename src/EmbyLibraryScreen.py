from os import path
from twisted.internet import threads
from enigma import eServiceReference, eTimer
from Screens.Screen import Screen
from Screens.InfoBar import InfoBar
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import config

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
from .Variables import plugin_dir
from . import _

from PIL import Image

MODE_RECOMMENDATIONS = 1
MODE_LIST = 2


class E2EmbyLibrary(Screen):
	skin = ["""<screen name="E2EmbyLibrary" position="fill">
					<widget name="header" position="center,30" size="700,50" font="Bold;32" transparent="1"/>
					<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="charbar" position="40,130" size="40,e-130-70" scrollbarMode="showNever" iconHeight="40" font="Regular;20" transparent="1" />
					<widget name="list" position="90,130" size="e-20-90,e-130-70" scrollbarMode="showOnDemand" iconWidth="225" iconHeight="315" orientation="orGrid" font="Regular;22" transparent="1" />
					<widget addon="Pager" connection="list" position="90,145+e-220+10" size="e-20-90,25" transparent="1" backgroundColor="background" zPosition="40" />
					<widget name="backdrop" position="e-1280,0" size="1280,720" alphatest="blend" zPosition="-3"/>
					<widget name="title_logo" position="60,140" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="subtitle" position="60,235" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
					<widget name="infoline" position="60,240" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="60,310" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="list_watching_header" position="55,570" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_watching" position="40,620" size="e-80,268" iconWidth="338" iconHeight="192" scrollbarMode="showNever" iconType="Thumb" orientation="orHorizontal" transparent="1" />
				</screen>"""]  # noqa: E124

	def __init__(self, session, library):
		Screen.__init__(self, session)
		self.exitResult = 0
		self.library = library
		self.library_id = int(library.get("Id", "0"))
		self.type = library.get("CollectionType")
		self.is_init = False
		self.selected_widget = "list_watching"
		self.last_item_id = None
		self.backdrop_pix = None
		self.mode = MODE_RECOMMENDATIONS
		self.plot_posy_orig = 310
		self.plot_height_orig = 168
		self.plot_width_orig = 924
		self.setTitle(_("Emby Library"))
		self.sel_timer = eTimer()
		self.sel_timer.callback.append(self.trigger_sel_changed_event)
		self.mask_alpha = Image.open(path.join(plugin_dir, "mask_l.png")).split()[3]
		if self.mask_alpha.mode != "L":
			self.mask_alpha = self.mask_alpha.convert("L")
		self.list_data = []
		self["header"] = EmbyLibraryHeaderButtons(self)
		self["charbar"] = EmbyLibraryCharacterBar()
		self["list"] = EmbyGridList()
		self["title_logo"] = Pixmap()
		self["title"] = Label()
		self["subtitle"] = Label()
		self["infoline"] = EmbyInfoLine(self)
		self["plot"] = Label()
		self["backdrop"] = Pixmap()
		self["backdrop_full"] = Pixmap()
		self["list_watching_header"] = Label(_("Continue watching"))
		self["list_watching"] = EmbyList()
		self.lists = {}
		self.lists["list_watching"] = EmbyListController(self["list_watching"], self["list_watching_header"])
		self["list_watching"].onSelectionChanged.append(self.onSelectedIndexChanged)
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
				"menu": self.menu
            }, -2)

	def __closeScreen(self):
		self.close(self.exitResult)

	def __onShown(self):
		if not self.is_init:
			self.is_init = True
			self["header"].setItem(self.library)
			threads.deferToThread(self.loadSuggestedTabItems)
			threads.deferToThread(self.loadItems)
			self["list"].hide()
			self["charbar"].hide()
			self["charbar"].enableSelection(False)
			self["list"].toggleSelection(False)
			self.lists["list_watching"].visible(True).enableSelection(True)

	def __onLayoutFinished(self):
		plot = self["plot"]
		plot_pos = plot.instance.position()
		plot_size = plot.instance.size()
		self.plot_posy_orig = plot_pos.y()
		self.plot_height_orig = plot_size.height()
		self.plot_width_orig = plot_size.width()

	def onSelectedIndexChanged(self, widget=None, item_id=None):
		self.last_item_id = self[self.selected_widget].selectedItem.get("Id")

		if not item_id:
			item_id = self[self.selected_widget].selectedItem.get("Id")

		self["backdrop"].setPixmap(None)
		self.backdrop_pix = None

		self.sel_timer.stop()
		self.sel_timer.start(config.plugins.e2embyclient.changedelay.value, True)

	def trigger_sel_changed_event(self):
		threads.deferToThread(self.loadSelectedItemDetails, self[self.selected_widget].selectedItem, self[self.selected_widget])

	def menu(self):
		if self.selected_widget == "charbar":
			self["charbar"].enableSelection(False)
		else:
			self[self.selected_widget].toggleSelection(False)
		self.selected_widget = "header"
		self[self.selected_widget].setFocused(True)

	def left(self):
		if self.selected_widget == "charbar" and self.mode == MODE_LIST:
			return
		if self.mode == MODE_LIST and self.selected_widget == "list" and self["list"].getIsAtFirstColumn():
			self.selected_widget = "charbar"
			self["list"].toggleSelection(False)
			self["charbar"].enableSelection(True)
			return

		if self.selected_widget == "header":
			self[self.selected_widget].movePrevious()
		else:
			if hasattr(self[self.selected_widget].instance, "prevItem"):
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.prevItem)
			else:
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveLeft)

	def right(self):
		if self.selected_widget == "charbar":
			self.selected_widget = "list"
			self["list"].toggleSelection(True)
			self["charbar"].enableSelection(False)
			return

		if self.selected_widget == "header":
			self[self.selected_widget].moveNext()
		else:
			if hasattr(self[self.selected_widget].instance, "nextItem"):
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.nextItem)
			else:
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveRight)

	def up(self):
		if self.selected_widget == "header":
			return

		if (self.selected_widget == "list" and self["list"].getIsAtFirstRow()) or self.selected_widget == "list_watching":
			self[self.selected_widget].toggleSelection(False)
			self.selected_widget = "header"
			self[self.selected_widget].setFocused(True)
		else:
			if self.selected_widget == "list":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveUp)
			elif self.selected_widget == "charbar":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.prevItem)
		# current_widget_index = self.availableWidgets.index(self.selected_widget)
		# if current_widget_index == 0:
		# 	return
		# y = self.top_slot_y

		# prevWidgetName = self.availableWidgets[current_widget_index - 1]
		# prevItem = self.lists[prevWidgetName]
		# prevItem.move(40, y).visible(True).enableSelection(True)
		# y += prevItem.getHeight() + 40
		# self.selected_widget = prevWidgetName

		# for item in self.availableWidgets[current_widget_index:]:
		# 	self.lists[item].move(40, y).enableSelection(False)
		# 	y += self.lists[item].getHeight() + 40

		# if self[self.selected_widget].isLibrary:
		# 	self.last_widget_info_load_success = None

		# self.onSelectedIndexChanged()

	def down(self):
		if self.selected_widget == "header":
			self[self.selected_widget].setFocused(False)
			self.selected_widget = "list_watching" if self.mode == MODE_RECOMMENDATIONS else "list"
			self[self.selected_widget].toggleSelection(True)
		else:
			if self.selected_widget == "list":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveDown)
			elif self.selected_widget == "charbar":
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.nextItem)
		# current_widget_index = self.availableWidgets.index(self.selected_widget)
		# if current_widget_index == len(self.availableWidgets) - 1:
		# 	return
		# safe_index = min(current_widget_index + 1, len(self.availableWidgets))
		# for item in self.availableWidgets[:safe_index]:
		# 	self.lists[item].visible(False).enableSelection(False)

		# y = self.top_slot_y
		# selEnabled = True
		# for item in self.availableWidgets[safe_index:]:
		# 	self.lists[item].move(40, y).enableSelection(selEnabled)
		# 	y += self.lists[item].getHeight() + 40
		# 	if selEnabled:
		# 		self.selected_widget = item
		# 	selEnabled = False
		# self.onSelectedIndexChanged()

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
			self.lists["list_watching"].visible(True)
		else:
			self["title_logo"].hide()
			self["title"].hide()
			self["subtitle"].hide()
			self["infoline"].hide()
			self["plot"].hide()
			self["backdrop"].hide()
			self.lists["list_watching"].visible(False)

	def processItem(self):
		if self.selected_widget == "header":
			selected_item = self[self.selected_widget].getSelectedButton()
			command = selected_item[2]
			if command == "recommend":
				self.mode = MODE_RECOMMENDATIONS
				self.toggleSuggestionSectionVisibility(True)
				self.toggleItemsSectionVisibility(False)
				# self.selected_widget = "list_watching"
				# self[self.selected_widget].toggleSelection(True)
			else:
				self.mode = MODE_LIST
				self.toggleSuggestionSectionVisibility(False)
				self.toggleItemsSectionVisibility(True)
				# self.selected_widget = "list"
				# self[self.selected_widget].toggleSelection(True)
		elif self.selected_widget == "charbar":
			char = self[self.selected_widget].selectedItem
			index = 0
			if char != "#":
				index = next((i for i, x in enumerate(self.list_data) if x[1].get("Name")[0].upper() == char), -1)
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
			self.session.openWithCallback(self.exitCallback, embyScreenClass, selected_item, self.mode == MODE_RECOMMENDATIONS and self.backdrop_pix)

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		self.exitResult = result
		threads.deferToThread(self.loadSuggestedTabItems)
		threads.deferToThread(self.loadItems)

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
		self.list_data = list
		self["charbar"].setList(list)

	def loadResumableItems(self):
		items = EmbyApiClient.getResumableItemsForLibrary(self.library_id, self.type)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list_watching"].loadData(list)

	def loadSuggestedTabItems(self):
		threads.deferToThread(self.loadResumableItems)

	def loadSelectedItemDetails(self, item, widget):
		if not self.is_init:
			return

		orig_item_id = item.get("Id")
		item_id = orig_item_id

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
			logo_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=logo_tag, max_width=max_w, max_height=max_h, image_type="Logo", format="png")
			if logo_pix:
				self["title_logo"].setPixmap(logo_pix)
				self["title"].text = ""
			else:
				if itemType == "Episode":
					self["title"].text = " ".join(item.get("SeriesName", "").splitlines())
				else:
					self["title"].text = " ".join(item.get("Name", "").splitlines())
				self["title_logo"].setPixmap(None)
		else:
			if itemType == "Episode":
				self["title"].text = " ".join(item.get("SeriesName", "").splitlines())
			else:
				self["title"].text = " ".join(item.get("Name", "").splitlines())
			self["title_logo"].setPixmap(None)

		if itemType == "Episode":
			sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
			self["subtitle"].text = sub_title
			subtitlesize = self["subtitle"].getSize()
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig + subtitlesize[1])
			self["plot"].resize(self.plot_width_orig, self.plot_height_orig - subtitlesize[1] - 20)
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(infolinepos.x(), self.plot_posy_orig + subtitlesize[1] - infolinesize[1] - 10)
		else:
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig)
			self["plot"].resize(self.plot_width_orig, self.plot_height_orig)
			self["subtitle"].text = ""
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(infolinepos.x(), self.plot_posy_orig - infolinesize[1] - 10)

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
		self.downloadCover(item_id, icon_img, orig_item_id)

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
