from enigma import eListbox, eListboxPythonMultiContent, RT_VALIGN_CENTER, RT_HALIGN_CENTER, eRect, RT_BLEND
from skin import parseColor, parseFont
from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryText, MultiContentEntryRectangle


class EmbyLibraryCharacterBar(GUIComponent):
	def __init__(self):
		GUIComponent.__init__(self)
		self.buttons = []
		self.selectedIndex = 0
		self.selectionEnabled = True
		self.data = []
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing = 10
		self.itemHeight = 35
		self.foreColor = None
		self.orientation = eListbox.orVertical
		self.l.setItemHeight(self.itemHeight)
		self.l.setItemWidth(35)

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

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value) in self.skinAttributes[:]:
			if attrib == "font":
				self.font = parseFont(value, parent.scale)
			elif attrib == "foregroundColor":
				self.foreColor = parseColor(value).argb()
			elif attrib == "spacing":
				self.spacing = int(value)
			elif attrib == "itemHeight":
				self.itemHeight = int(value)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		self.l.setItemHeight(self.itemHeight)
		return GUIComponent.applySkin(self, desktop, parent)

	def setList(self, list):
		self.buttons = sorted({s[1].get("Name")[0].upper() if not s[1].get("Name")[0].isdigit() else "#" for s in list if s[1].get("Name")}, key=lambda c: (
			c.isascii() and c.isalpha(),  # False for non-English letters → comes first
			c.upper()                     # Sort alphabetically within each group
		))
		self.updateInfo()

	def updateInfo(self):
		l_list = []
		i = 0
		for button in self.buttons:
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

	def buildEntry(self, index, text):
		xPos = 0
		yPos = 0
		width = self.instance.size().width()
		selected = self.selectedIndex == index and self.selectionEnabled
		res = [None]
		if selected:
			res.append(MultiContentEntryRectangle(
				pos=(2, 2), size=(width - 4, self.itemHeight - 4),
				cornerRadius=6,
				backgroundColor=0x32772b, backgroundColorSelected=0x32772b))

		res.append(MultiContentEntryText(
			pos=(xPos + 2, yPos + 2), size=(width - 4, self.itemHeight - 4),
			font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
			text=text,
			color=self.foreColor, color_sel=self.foreColor))

		return res
