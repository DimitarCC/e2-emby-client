from Components.GUIComponent import GUIComponent
from enigma import eListbox, eListboxPythonMultiContent, eRect, BT_SCALE, BT_KEEP_ASPECT_RATIO, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, RT_VALIGN_TOP, RT_HALIGN_CENTER, RT_BLEND, RT_WRAP
from skin import parseColor, parseFont
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryProgress, MultiContentEntryRectangle
from .Variables import REQUEST_USER_AGENT
from .EmbyRestClient import EmbyApiClient

from twisted.internet import threads


class EmbyList(GUIComponent):
	def __init__(self):
		GUIComponent.__init__(self)
		self.data = []
		self.itemsForThumbs = []
		self.selectionEnabled = True
		self.font = gFont("Regular", 18)
		self.selectedItem = None
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing_sides = 15
		self.orientations = {"orHorizontal": eListbox.orHorizontal, "orVertical": eListbox.orVertical}
		self.orientation = eListbox.orHorizontal
		self.iconWidth = 270
		self.iconHeight = 152
		self.itemWidth = self.iconWidth + self.spacing_sides*2
		self.itemHeight = self.iconHeight + 72
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(self.itemWidth)
		self.icon_type = "Primary"
		self.refreshing = False
		self.running = False
		self.updatingIndexesInProgress = []
		# self.l.setOrientation(self.orientation)
		threads.deferToThread(self.runQueueProcess)

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)
		self.l.setSelectionClip(eRect(0, 0, 0, 0), False)

	def preWidgetRemove(self, instance):
		instance.selectionChanged.get().remove(self.selectionChanged)
		

	def selectionChanged(self):
		self.selectedItem = self.l.getCurrentSelection()

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value) in self.skinAttributes[:]:
			if attrib == "orientation":
				self.orientation = self.orientations.get(value, self.orientations["orHorizontal"])
			elif attrib == "font":
				self.font = parseFont(value, parent.scale)
			elif attrib == "foregroundColor":
				self.foreColor = parseColor(value).argb()
			elif attrib == "iconType":
				self.icon_type = value
			elif attrib == "iconWidth":
				self.iconWidth = int(value)
			elif attrib == "iconHeight":
				self.iconHeight = int(value)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.itemWidth = self.iconWidth + self.spacing_sides*2
		self.itemHeight = self.iconHeight + 72
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(self.itemWidth)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		return GUIComponent.applySkin(self, desktop, parent)
	
	def toggleSelection(self, enabled):
		self.selectionEnabled = enabled
		self.instance.setSelectionEnable(enabled)

	def getCurrentItem(self):
		cur = self.l.getCurrentSelection()
		return cur and cur[1]

	def loadData(self, items):
		self.data = items
		self.l.setList(items)

	def runQueueProcess(self):
		self.running = True
		while len(self.itemsForThumbs) > 0:
			item_popped = self.itemsForThumbs.pop(-1)
			item_index = item_popped[0]
			item = item_popped[1]
			icon_img = item.get("ImageTags").get("Primary")
			item_id = item.get("Id")
			parent_id = item.get("ParentThumbItemId")
			parent_icon_img = item.get("ParentThumbImageTag")
			if parent_id and parent_icon_img:
				item_id = parent_id
				icon_img = parent_icon_img
				self.icon_type = "Thumb"
			
			if item_index not in self.updatingIndexesInProgress:
				threads.deferToThread(self.updateThumbnail, item_id, item_index, item, icon_img, False)

		self.running = False
			

	def updateThumbnail(self, item_id, item_index, item, icon_img, fromRecursion):
		icon_pix = None

		if item_index not in self.updatingIndexesInProgress:
			self.updatingIndexesInProgress.append(item_index)

		icon_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight, image_type=self.icon_type)
		if not icon_pix:
			backdrop_image_tags = item.get("BackdropImageTags")
			parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
			if parent_backdrop_image_tags:
				backdrop_image_tags = parent_backdrop_image_tags
			
			if not backdrop_image_tags or len(backdrop_image_tags) == 0:
				return False

			icon_img = backdrop_image_tags[0]
			parent_b_item_id = item.get("ParentBackdropItemId")
			if parent_b_item_id:
				item_id = parent_b_item_id
			if not icon_pix:
				icon_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight, image_type="Backdrop")

		if not hasattr(self, "data"):
			return False
		if not self.data[item_index][3]:
			self.data[item_index] = (item_index, item, self.data[item_index][2], icon_pix or True, self.data[item_index][4], self.data[item_index][5])
			
		if item_index in self.updatingIndexesInProgress:
			self.updatingIndexesInProgress.remove(item_index)

		self.loadData(self.data)
		return True

	def buildEntry(self, item_index, item, item_name, item_icon, played_perc, has_backdrop):
		xPos = 0
		yPos = 0
		res = [None]
		selected = self.selectedItem and self.selectedItem[1] == item
		if selected and self.selectionEnabled:
			res.append(MultiContentEntryRectangle(
					pos=(self.spacing_sides - 3, self.spacing_sides - 3), size=(self.iconWidth + 6, self.iconHeight + 6),
					cornerRadius=8,
					backgroundColor=0x32772b, backgroundColorSelected=0x32772b))
		is_icon = not isinstance(item_icon, bool)
		if item_icon and is_icon:
			res.append(MultiContentEntryPixmapAlphaBlend(
							pos=(self.spacing_sides, self.spacing_sides),
							size=(self.iconWidth, self.iconHeight),
							png=item_icon,
							backcolor=None, backcolor_sel=None, 
							cornerRadius=6,
							flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
		else:
			found = any(item_index in tup for tup in self.itemsForThumbs)
			if is_icon and not found:
				self.itemsForThumbs.append((item_index, item))
			if len(self.itemsForThumbs) > 0 and not self.running:
				threads.deferToThread(self.runQueueProcess)
			res.append(MultiContentEntryRectangle(
					pos=(self.spacing_sides, self.spacing_sides),
					size=(self.iconWidth, self.iconHeight),
					cornerRadius=6,
					backgroundColor=0x22222222))
			
		played_perc = int(played_perc)
		cornerEdges = 12
		if played_perc < 90:
			cornerEdges = 4
		if played_perc > 0:
			res.append(MultiContentEntryProgress(
				pos=(self.spacing_sides, self.spacing_sides + self.iconHeight - 6), size=(self.iconWidth, 6),
				percent= played_perc, foreColor=0x32772b, foreColorSelected=0x32772b, borderWidth=0, cornerRadius=6, cornerEdges=cornerEdges
			))
			
		res.append(MultiContentEntryText(
							pos=(self.spacing_sides, self.iconHeight + 32), size=(self.iconWidth, 60),
							font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_WRAP,
							cornerRadius=6,
							text=item_name, 
							color=0xffffff, color_sel=0xffffff))
		
		return res
	
		

		




