from time import sleep
from uuid import uuid4

from twisted.internet import threads

from enigma import eTimer, eListbox, eListboxPythonMultiContent, eRect, BT_SCALE, BT_KEEP_ASPECT_RATIO, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, RT_BLEND, RT_ELLIPSIS
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryRectangle
from Tools.LoadPixmap import LoadPixmap

from .EmbyRestClient import EmbyApiClient, DIRECTORY_PARSER
from .HelperFunctions import create_thumb_cache_dir, delete_thumb_cache_dir


class EmbyMusicRowList(GUIComponent):
	def __init__(self):
		GUIComponent.__init__(self)
		self.widget_id = uuid4()
		self.selectedIndex = -1
		self.data = []
		self.itemsForThumbs = []
		self.itemsForRedraw = []
		self.itemsForRedrawDelayed = []
		self.thumbs = {}
		self.onSelectionChanged = []
		self.selectionEnabled = True
		self.font = gFont("Regular", 24)
		self.badgeFont = gFont("Regular", 20)
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing = 12
		self.columns = 3
		self.orientation = eListbox.orGrid
		self.iconHeight = 64
		self.itemWidth = 0
		self.itemHeight = self.iconHeight + self.spacing * 2
		self.l.setItemHeight(self.itemHeight)
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

	def getMoveLeftAction(self):
		if hasattr(self.instance, "prevItem"):
			return self.instance.prevItem
		return self.instance.moveLeft

	moveLeft = property(getMoveLeftAction)

	def getMoveRightAction(self):
		if hasattr(self.instance, "nextItem"):
			return self.instance.nextItem
		return self.instance.moveRight

	moveRight = property(getMoveRightAction)

	def getIsAtFirstRow(self):
		return (self.l.getCurrentSelectionIndex() // self.columns) == 0

	def getIsAtLastRow(self):
		if not self.data:
			return True
		last_row = (len(self.data) - 1) // self.columns
		return (self.l.getCurrentSelectionIndex() // self.columns) == last_row

	def getIsAtFirstColumn(self):
		return (self.l.getCurrentSelectionIndex() % self.columns) == 0

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

	def isIndexInCurrentPage(self, index):
		if self.items_per_page == 0:
			return True
		return (index // self.items_per_page) == self.currentPage

	def selectionChanged(self):
		curIndex = self.l.getCurrentSelectionIndex()
		if self.selectedIndex == curIndex:
			return
		self.selectedIndex = curIndex
		if self.items_per_page:
			newPage = self.selectedIndex // self.items_per_page
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
				elif attrib == "iconHeight":
					self.iconHeight = int(value)
				elif attrib == "columns":
					self.columns = int(value)
				elif attrib == "spacing":
					self.spacing = int(value)
				else:
					attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.l.setFont(1, self.badgeFont)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		res = GUIComponent.applySkin(self, desktop, parent)
		size = self.instance.size()
		self.itemWidth = max(size.width() // self.columns, 1)
		self.itemHeight = self.iconHeight + self.spacing * 2
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(self.itemWidth)
		rows = max(size.height() // self.itemHeight, 1)
		self.items_per_page = self.columns * rows
		return res

	def toggleSelection(self, enabled):
		self.selectionEnabled = enabled
		self.instance.setSelectionEnable(enabled)

	def getCurrentItem(self):
		cur = self.l.getCurrentSelection()
		return cur and cur[1] or {}

	# Live-computed, like EmbyList.selectedItem - a plain attribute only
	# updated by the native selectionChanged signal (as EmbyGridList uses)
	# reads stale/None right after loadData()/toggleSelection(), which is
	# exactly when EmbyLibraryScreen.onSelectedIndexChanged() needs it for
	# rows used in MODE_RECOMMENDATIONS (the backdrop/info pane).
	selectedItem = property(getCurrentItem)

	def loadData(self, items):
		self.data = items
		self.l.setList(items)
		for x in self.onSelectionChanged:
			x()

	def runQueueProcess(self):
		self.running = True
		while len(self.itemsForThumbs) > 0:
			if self.interupt:
				self.interupt = False
				break
			item_index, item = self.itemsForThumbs.pop(0)
			if not self.isIndexInCurrentPage(item_index):
				continue
			threads.deferToThread(self.updateThumbnail, item_index, item)
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
			self.instance.redrawItemByIndex(item_index)
		self.redrawing_thread_running = False

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

	def updateThumbnail(self, item_index, item):
		if not self.isIndexInCurrentPage(item_index):
			return

		orig_id = item.get("Id")

		if item_index not in self.updatingIndexesInProgress:
			self.updatingIndexesInProgress.append(item_index)

		item_id = orig_id
		icon_img = (item.get("ImageTags") or {}).get("Primary")
		if not icon_img:
			album_id = item.get("AlbumId")
			album_tag = item.get("AlbumPrimaryImageTag")
			if album_id and album_tag:
				item_id = album_id
				icon_img = album_tag

		icon_pix = None
		if icon_img:
			icon_pix = EmbyApiClient.getItemImage(widget_id=self.widget_id, item_id=item_id, logo_tag=icon_img, width=self.iconHeight, height=self.iconHeight, image_type="Primary")

		if not self.isIndexInCurrentPage(item_index):
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
		selected = self.selectedIndex == item_index
		if orig_id in self.thumbs:
			item_icon = self.thumbs[orig_id]
			if item_index in self.itemsForRedrawDelayed:
				self.itemsForRedrawDelayed.remove(item_index)
				if len(self.itemsForRedrawDelayed) > 0 and not self.redraw_timer.isActive():
					self.redraw_timer.start(1000)

		sel = selected and self.selectionEnabled
		cardWidth = self.itemWidth - self.spacing
		res.append(MultiContentEntryRectangle(
			pos=(4, 4), size=(cardWidth - 4, self.itemHeight - 8),
			cornerRadius=8,
			backgroundColor=0x32772b if sel else 0x1e1e1e, backgroundColorSelected=0x32772b))

		is_icon = not isinstance(item_icon, bool)
		if item_icon and is_icon:
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(self.spacing, self.spacing),
				size=(self.iconHeight, self.iconHeight),
				png=LoadPixmap(item_icon),
				cornerRadius=4,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
		else:
			found = any(item_index in tup for tup in self.itemsForThumbs)
			if is_icon and not found:
				self.itemsForThumbs.append((item_index, item))
			if len(self.itemsForThumbs) > 0 and not self.running:
				threads.deferToThread(self.runQueueProcess)

		text_x = self.spacing * 2 + self.iconHeight
		text_width = cardWidth - text_x - self.spacing
		artist = item.get("AlbumArtist") or ", ".join(item.get("Artists") or []) or item.get("Album", "")

		res.append(MultiContentEntryText(
			pos=(text_x, self.spacing), size=(text_width, 28),
			font=0, flags=RT_HALIGN_LEFT | RT_BLEND | RT_VALIGN_CENTER | RT_ELLIPSIS,
			text=item_name,
			color=0xffffff, color_sel=0xffffff))
		res.append(MultiContentEntryText(
			pos=(text_x, self.spacing + 28), size=(text_width, 24),
			font=1, flags=RT_HALIGN_LEFT | RT_BLEND | RT_VALIGN_CENTER | RT_ELLIPSIS,
			text=artist,
			color=0xaaaaaa, color_sel=0xdedede))

		self.index_currently_redrawing = -1
		return res
