from time import sleep
from uuid import uuid4

from twisted.internet import threads

from enigma import eTimer, eListbox, eListboxPythonMultiContent, eRect, BT_SCALE, BT_KEEP_ASPECT_RATIO, BT_HALIGN_CENTER, BT_VALIGN_CENTER, gFont, RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_BLEND, RT_WRAP, RT_ELLIPSIS
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryProgress, MultiContentEntryRectangle
from Components.config import config
from Tools.LoadPixmap import LoadPixmap

from .EmbyRestClient import EmbyApiClient, DIRECTORY_PARSER
from .HelperFunctions import embyDateToString, create_thumb_cache_dir, delete_thumb_cache_dir
from .Variables import plugin_dir, EMBY_THUMB_CACHE_DIR
from . import _


class EmbyGridList(GUIComponent):
	def __init__(self, isLibrary=False):
		GUIComponent.__init__(self)
		self.widget_id = uuid4()
		self.currentSelectedIndex = 0
		self.isLibrary = isLibrary
		self.data = []
		self.itemsForThumbs = []
		self.itemsForRedraw = []
		self.itemsForRedrawDelayed = []
		self.thumbs = {}
		self.onSelectionChanged = []
		self.check24 = LoadPixmap("%s/check_24.png" % plugin_dir)
		self.selectionEnabled = True
		self.font = gFont("Regular", 18)
		self.badgeFont = gFont("Regular", 18)
		self.selectedItem = None
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing = 15
		self.orientation = eListbox.orGrid
		self.iconWidth = 200
		self.iconHeight = 260
		self.itemWidth = self.iconWidth + self.spacing * 2
		self.itemHeight = self.iconHeight + 90 + self.spacing * 2
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(self.itemWidth)
		self.icon_type = "Primary"
		self.refreshing = False
		self.running = False
		self.redrawing_thread_running = False
		self.index_currently_redrawing = -1
		self.updatingIndexesInProgress = []
		self.interupt = False
		self.currentPage = 0
		self.items_per_page = 0
		self.redraw_timer = eTimer()
		self.redraw_timer.callback.append(self.redraw_delayed)
		self.redraw_timer.start(1000)

	GUI_WIDGET = eListbox

	def getListCount(self):
		max_columns = self.instance.size().width() // self.itemWidth
		return (len(self.data) + max_columns - 1) // max_columns

	# for use with the pager addon. Returns total rows count
	listCount = property(getListCount)

	def getCurrentRow(self):
		max_columns = self.instance.size().width() // self.itemWidth
		return self.currentSelectedIndex // max_columns

	# for use with the pager addon. Returns index of current row
	currentIndex = property(getCurrentRow)

	def onShow(self):
		pass

	def redraw_delayed(self):
		for index in list(self.itemsForRedrawDelayed):
			if self.interupt:
				break
			if len(self.itemsForRedrawDelayed) == 0:
				self.redraw_timer.stop()
				break
			if not self.isIndexInCurrentPage(index):
				continue
			if index not in self.itemsForRedrawDelayed:
				continue

			self.instance.redrawItemByIndex(index)

	def postWidgetCreate(self, instance):
		create_thumb_cache_dir(self.widget_id)
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)
		instance.allowNativeKeys(False)
		self.l.setSelectionClip(eRect(0, 0, 0, 0), False)

		threads.deferToThread(self.runQueueProcess)

	def preWidgetRemove(self, instance):
		instance.selectionChanged.get().remove(self.selectionChanged)
		self.redraw_timer.stop()
		self.redraw_timer.callback.remove(self.redraw_delayed)
		self.interupt = True
		delete_thumb_cache_dir(self.widget_id)

	def getIndexCurrentPage(self, index):
		return index // self.items_per_page

	def isIndexInCurrentPage(self, index):
		item_page_index = index // self.items_per_page
		min = self.currentPage
		max = self.currentPage
		return item_page_index >= min and item_page_index <= max

	def getIsAtFirstRow(self):
		size = self.instance.size()
		width = size.width()
		cols = width // self.itemWidth
		curRow = self.currentSelectedIndex // cols
		return curRow == 0

	def getIsAtFirstColumn(self):
		size = self.instance.size()
		width = size.width()
		cols = width // self.itemWidth
		curCol = self.currentSelectedIndex % cols
		return curCol == 0

	def selectionChanged(self):
		self.selectedItem = self.l.getCurrentSelection()
		self.currentSelectedIndex = self.l.getCurrentSelectionIndex()
		newPage = self.getIndexCurrentPage(self.currentSelectedIndex)
		if self.currentPage != newPage:
			self.currentPage = newPage
		for x in self.onSelectionChanged:
			x()

	def applySkin(self, desktop, parent):
		attribs = []
		if self.skinAttributes is not None:
			for (attrib, value) in self.skinAttributes[:]:
				if attrib == "font":
					self.font = parseFont(value, parent.scale)
				elif attrib == "badgeFont":
					self.badgeFont = parseFont(value, parent.scale)
				elif attrib == "foregroundColor":
					self.foreColor = parseColor(value).argb()
				elif attrib == "iconType":
					self.icon_type = value
				elif attrib == "iconWidth":
					self.iconWidth = int(value)
				elif attrib == "iconHeight":
					self.iconHeight = int(value)
				elif attrib == "spacing":
					self.spacing = int(value)
				else:
					attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.l.setFont(1, self.badgeFont)
		self.itemWidth = self.iconWidth + self.spacing * 2
		self.itemHeight = self.iconHeight + 90 + self.spacing * 2
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(self.itemWidth)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		res = GUIComponent.applySkin(self, desktop, parent)
		size = self.instance.size()
		width = size.width()
		height = size.height()
		cols = width // self.itemWidth
		rows = height // self.itemHeight
		self.items_per_page = cols * rows
		return res

	def toggleSelection(self, enabled):
		self.selectionEnabled = enabled
		self.instance.setSelectionEnable(enabled)

	def getCurrentItem(self):
		cur = self.l.getCurrentSelection()
		return cur and cur[1]

	def loadData(self, items):
		self.data = items
		if config.plugins.e2embyclient.thumbcache_loc.value != "off":
			for item in items:
				itm = item[1]
				item_id = itm.get("Id")
				icon_img = itm.get("ImageTags").get("Primary")
				parent_icon_img = itm.get("ParentThumbImageTag")
				if parent_icon_img:
					icon_img = parent_icon_img
				f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{item_id}_{self.iconWidth}x{self.iconHeight}_{icon_img}__{self.iconWidth}_{self.iconHeight}.jpg"
				if f_name in DIRECTORY_PARSER.THUMBS:
					self.thumbs[item_id] = f_name
		self.l.setList(items)

	def get_page_item_ids(self, page_index):
		start = page_index * self.items_per_page
		end = min(start + self.items_per_page, len(self.data))
		return [(item[0], item[1]) for item in self.data[start:end]]

	def runQueueProcess(self):
		self.running = True
		while len(self.itemsForThumbs) > 0:
			if self.interupt:
				self.interupt = False
				break
			item_popped = self.itemsForThumbs.pop(0)
			item_index = item_popped[0]
			if not self.isIndexInCurrentPage(item_index):
				continue
			item = item_popped[1]
			icon_img = item.get("ImageTags").get("Primary")
			item_id = item.get("Id")
			parent_id = item.get("ParentThumbItemId")
			parent_icon_img = item.get("ParentThumbImageTag")
			if parent_id and parent_icon_img:
				item_id = parent_id
				icon_img = parent_icon_img
				self.icon_type = "Thumb"

			threads.deferToThread(self.updateThumbnail, item_id, item_index, item, icon_img, False)

		self.running = False

	def runRedrawingQueueProcess(self):
		self.redrawing_thread_running = True
		while len(self.itemsForRedraw) > 0:
			if self.interupt:
				self.interupt = False
				break
			while self.index_currently_redrawing > -1:
				sleep(0.15)
				continue
			item_index = self.itemsForRedraw.pop(0)
			print("[E2Emby][EmbyGridList] DELAYED REDRAW OF THUMB")
			self.instance.redrawItemByIndex(item_index)

		self.redrawing_thread_running = False

	def updateThumbnail(self, item_id, item_index, item, icon_img, fromRecursion):
		icon_pix = None

		if not self.isIndexInCurrentPage(item_index):
			return

		orig_id = item.get("Id")

		if item_index not in self.updatingIndexesInProgress:
			self.updatingIndexesInProgress.append(item_index)

		icon_pix = EmbyApiClient.getItemImage(widget_id=self.widget_id, item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight, image_type=self.icon_type)
		if not self.isIndexInCurrentPage(item_index):
			return
		if not icon_pix:
			backdrop_image_tags = item.get("BackdropImageTags")
			parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
			if parent_backdrop_image_tags:
				backdrop_image_tags = parent_backdrop_image_tags

			if not backdrop_image_tags or len(backdrop_image_tags) == 0:
				return

			icon_img = backdrop_image_tags[0]
			parent_b_item_id = item.get("ParentBackdropItemId")
			if parent_b_item_id:
				item_id = parent_b_item_id

			icon_pix = EmbyApiClient.getItemImage(widget_id=self.widget_id, item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight, image_type="Backdrop")
			if not self.isIndexInCurrentPage(item_index):
				return

		if not hasattr(self, "data"):
			return
		if orig_id not in self.thumbs:
			self.thumbs[orig_id] = icon_pix or True
			if item_index not in self.itemsForRedrawDelayed:
				self.itemsForRedrawDelayed.append(item_index)
				if not self.redraw_timer.isActive():
					self.redraw_timer.start(1000)

		if item_index in self.updatingIndexesInProgress:
			self.updatingIndexesInProgress.remove(item_index)

		if icon_pix:
			DIRECTORY_PARSER.addToSet(icon_pix)
			threads.deferToThread(self.redrawItem, item_index)

	def redrawItem(self, index):
		if self.index_currently_redrawing > -1:
			self.itemsForRedraw.append(index)
			if len(self.itemsForRedraw) == 1 and not self.redrawing_thread_running:
				threads.deferToThread(self.runRedrawingQueueProcess)
		else:
			self.instance.redrawItemByIndex(index)

	def buildEntry(self, item_index, item, item_name, item_icon, played_perc, has_backdrop):
		self.index_currently_redrawing = item_index
		res = [None]
		orig_id = item.get("Id")
		selected = self.currentSelectedIndex == item_index
		if orig_id in self.thumbs:
			item_icon = self.thumbs[orig_id]
			if item_index in self.itemsForRedrawDelayed:
				self.itemsForRedrawDelayed.remove(item_index)
				if len(self.itemsForRedrawDelayed) > 0 and not self.redraw_timer.isActive():
					self.redraw_timer.start(1000)
		sel = selected and self.selectionEnabled
		res.append(MultiContentEntryRectangle(
			pos=(self.spacing - 3, self.spacing - 3), size=(self.iconWidth + 6, self.iconHeight + 6),
			cornerRadius=8,
			borderWidth=3, borderColor=0x32772b if sel else 0xfe555555, borderColorSelected=0x32772b if sel else 0xfe555555,
			backgroundColor=0x02222222, backgroundColorSelected=0x02222222))

		is_icon = not isinstance(item_icon, bool)
		if item_icon and is_icon:
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(self.spacing, self.spacing),
				size=(self.iconWidth, self.iconHeight),
				png=LoadPixmap(item_icon),
				cornerRadius=6,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
		else:
			found = any(item_index in tup for tup in self.itemsForThumbs)
			if is_icon and not found:
				self.itemsForThumbs.append((item_index, item))
			if len(self.itemsForThumbs) > 0 and not self.running:
				threads.deferToThread(self.runQueueProcess)

		played_perc = int(played_perc)
		cornerEdges = 12
		if played_perc < 90:
			cornerEdges = 4
		if played_perc > 0:
			res.append(MultiContentEntryProgress(
				pos=(self.spacing, self.spacing + self.iconHeight - 6), size=(self.iconWidth, 6),
				percent=played_perc, foreColor=0x32772b, foreColorSelected=0x32772b, borderWidth=0, cornerRadius=6, cornerEdges=cornerEdges
			))

		premiereDate_str = item.get("PremiereDate", None)
		premiereDate = premiereDate_str and embyDateToString(
			premiereDate_str, "Movie")

		text = f"{item_name}"
		text1 = ""
		if premiereDate:
			text1 = f"({premiereDate})"

		res.append(MultiContentEntryText(
			pos=(self.spacing, self.iconHeight + 32), size=(self.iconWidth, 25),
			font=0, flags=RT_HALIGN_CENTER | RT_BLEND,
			text=text,
			color=0xffffff, color_sel=0xffffff))
		if text1:
			res.append(MultiContentEntryText(
				pos=(self.spacing, self.iconHeight + 62), size=(self.iconWidth, 25),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND,
				text=text1,
				color=0xc2c2c2, color_sel=0xc2c2c2))

		played = item.get("UserData", {}).get("Played", False)
		unplayed_items_count = item.get("UserData", {}).get("UnplayedItemCount", -1)
		if played:
			res.append(MultiContentEntryRectangle(
				pos=(self.spacing + self.iconWidth - 45, self.spacing),
				size=(45, 45),
				cornerRadius=6,
				cornerEdges=2 | 4,
				backgroundColor=0x32772b, backgroundColorSelected=0x32772b))
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(self.spacing + self.iconWidth - 45, self.spacing),
				size=(45, 45),
				png=self.check24,
				cornerRadius=6,
				flags=BT_HALIGN_CENTER | BT_VALIGN_CENTER))
		elif unplayed_items_count > 0:
			res.append(MultiContentEntryText(
				pos=(self.spacing + self.iconWidth - 45, self.spacing),
				size=(45, 45),
				font=1, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=str(unplayed_items_count),
				cornerRadius=6,
				cornerEdges=2 | 4,
				backcolor=0x32772b, backcolor_sel=0x32772b,
				textBColor=0x222222, textBWidth=1,
				color=0xffffff, color_sel=0xffffff))
		self.index_currently_redrawing = -1
		return res
