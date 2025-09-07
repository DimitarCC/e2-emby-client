from enigma import eListbox, eListboxPythonMultiContent, RT_VALIGN_CENTER, RT_HALIGN_CENTER, eRect, RT_BLEND, gFont
from skin import parseColor, parseFont
from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryText, MultiContentEntryRectangle


class EmbySeasonsBar(GUIComponent):
	def __init__(self):
		GUIComponent.__init__(self)
		self.seasons = []
		self.selectedIndex = 0
		self.selectionEnabled = False
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.font = gFont("Regular", 18)
		self.spacing = 10
		self.itemWidth = 35
		self.foreColor = None
		self.orientation = eListbox.orHorizontal
		self.l.setItemHeight(35)
		self.l.setItemWidth(self.itemWidth)

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setSelectionEnable(False)
		instance.setContent(self.l)
		instance.allowNativeKeys(False)
		instance.selectionChanged.get().append(self.selectionChanged)
		self.l.setSelectionClip(eRect(0, 0, 0, 0), False)

	def preWidgetRemove(self, instance):
		instance.selectionChanged.get().remove(self.selectionChanged)

	def onContainerShown(self):
		self.l.setItemHeight(self.instance.size().height())
		self.l.setItemWidth(self.instance.size().width())

	def selectionChanged(self):
		self.selectedIndex = self.l.getCurrentSelectionIndex()

	def getCurrentItem(self):
		cur = self.l.getCurrentSelection()
		return cur and cur[1] or {}

	selectedItem = property(getCurrentItem)

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

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value) in self.skinAttributes[:]:
			if attrib == "font":
				self.font = parseFont(value, parent.scale)
			elif attrib == "foregroundColor":
				self.foreColor = parseColor(value).argb()
			elif attrib == "spacing":
				self.spacing = int(value)
			elif attrib == "itemWidth":
				self.itemWidth = int(value)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		self.l.setItemWidth(self.itemWidth)
		return GUIComponent.applySkin(self, desktop, parent)

	def setList(self, list):
		self.seasons = list
		self.updateInfo()

	def updateInfo(self):
		l_list = []
		i = 0
		for button in self.seasons:
			l_list.append((i, button))
			i += 1
		self.l.setList(l_list)

	def enableSelection(self, selection):
		if not selection:
			self.selectedIndex = 0
		self.selectionEnabled = selection
		self.instance.setSelectionEnable(selection)
		self.updateInfo()

	def getSize(self):
		s = self.instance.size()
		return s.width(), s.height()

	def buildEntry(self, index, item):
		xPos = 0
		yPos = 0
		height = self.instance.size().height()
		selected = self.selectedIndex == index
		text = item[2]
		res = [None]

		res.append(MultiContentEntryText(
			pos=(xPos + 4, yPos + 2), size=(self.itemWidth - 8, height - 4),
			font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
			text=text,
			cornerRadius=6,
			textBWidth=1 if selected and self.selectionEnabled else 0, textBColor=0x222222,
			backcolor=0x32772b if (selected and self.selectionEnabled) else 0x222222,
			border_width=2, border_color=0x32772b if selected else 0x404040,
			color=self.foreColor, color_sel=self.foreColor))

		return res
