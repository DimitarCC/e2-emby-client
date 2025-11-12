from enigma import eLabel, eListbox, eListboxPythonMultiContent, BT_SCALE, BT_KEEP_ASPECT_RATIO, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER, RT_HALIGN_CENTER, getDesktop, eSize, RT_ELLIPSIS, RT_BLEND
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryRectangle
from Tools.Directories import resolveFilename, SCOPE_GUISKIN
from Tools.LoadPixmap import LoadPixmap

from . import _


class EmbyPlayerInfobarInfo(GUIComponent):
	def __init__(self, screen):
		GUIComponent.__init__(self)
		self.screen = screen
		self.screen.onShow.append(self.onContainerShown)
		self.item = {}
		self.curAtrackIndex = 0
		self.curSubsIndex = -1
		self.is_trailer = False
		self.font = gFont("Regular", 18)
		self.fontAdditional = gFont("Regular", 18)
		self.foreColorAdditional = 0xffffff
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing = 10
		self.orientation = eListbox.orHorizontal
		self.l.setItemHeight(35)
		self.l.setItemWidth(35)

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setSelectionEnable(False)
		instance.setContent(self.l)
		instance.allowNativeKeys(False)

	def onContainerShown(self):
		self.l.setItemHeight(self.instance.size().height())
		self.l.setItemWidth(self.instance.size().width())

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value) in self.skinAttributes[:]:
			if attrib == "font":
				self.font = parseFont(value, parent.scale)
			elif attrib == "fontAdditional":
				self.fontAdditional = parseFont(value, parent.scale)
			elif attrib == "foregroundColor":
				self.foreColor = parseColor(value).argb()
			elif attrib == "foregroundColorAdditional":
				self.foreColorAdditional = parseColor(value).argb()
			elif attrib == "spacing":
				self.spacing = int(value)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.l.setFont(1, self.fontAdditional)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		return GUIComponent.applySkin(self, desktop, parent)

	def updateInfo(self, item, aIndex, sIndex, is_trailer=False):
		self.curAtrackIndex = aIndex
		self.curSubsIndex = sIndex
		self.is_trailer = is_trailer
		self.item = item
		l_list = []
		l_list.append((item,))
		self.l.setList(l_list)

	def _calcTextWidth(self, text, font=None, size=None):
		size = eLabel.calculateTextSize(font, text, size)
		res_width = size.width()
		res_height = size.height()
		return res_width, res_height

	def getDesktopWith(self):
		return getDesktop(0).size().width()

	def getSize(self):
		s = self.instance.size()
		return s.width(), s.height()

	def getTitle(self):
		type = self.item.get("Type")
		title = ""
		if type == "Episode":
			title = f"{self.item.get("SeriesName", "")} • S{self.item.get("ParentIndexNumber", 0)}:E{self.item.get("IndexNumber", 0)} • {" ".join(self.item.get("Name", "").splitlines())}"
		else:
			title = " ".join(self.item.get("Name", "").splitlines())

		if self.is_trailer:
			return f"{title} - Trailer"
		return title

	def constructLabelBox(self, res, header, text, height, xPos, yPos, spacing=None, borderColor=0x757472, backColor=0x55111111, textColor=0xffffff):
		if not spacing:
			spacing = self.spacing

		headerWidth = self._calcTextWidth(header, font=self.fontAdditional, size=eSize(self.getDesktopWith() // 3, 0))[0] if header else 0

		textWidth, textHeight = self._calcTextWidth(text, font=self.fontAdditional, size=eSize(self.getDesktopWith() // 3, 0))
		rec_height = textHeight + 10
		xPos -= spacing + textWidth + headerWidth + 30 + (26 if headerWidth else 0)
		if headerWidth:
			res.append(MultiContentEntryText(
				pos=(xPos + 1, yPos + (height - rec_height) // 2 + 1), size=(headerWidth + 26, rec_height + 1),
				font=1, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER | RT_BLEND,
				text=header,
				cornerRadius=4,
				cornerEdges=1 | 4,
				border_color=borderColor, border_width=1,
				backcolor=0x02333333, backcolor_sel=0x02333333,
				color=textColor, color_sel=textColor))

		res.append(MultiContentEntryText(
			pos=(xPos + headerWidth + (26 if headerWidth else 0), yPos + (height - rec_height) // 2 + 1), size=(textWidth + 26, rec_height + 1),
			font=1, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER | RT_BLEND,
			text=text,
			cornerRadius=4,
			cornerEdges=2 | 8 if headerWidth else 15,
			border_color=borderColor, border_width=1,
			backcolor=backColor, backcolor_sel=backColor,
			color=textColor, color_sel=textColor))

		return xPos

	def constructResolutionLabel(self):
		width = int(self.item.get("Width", "0"))
		height = int(self.item.get("Height", "0"))
		if width == 0 or height == 0:
			return ""

		if height > 1080 and width > 1920:
			return "UHD"

		if (height > 720 or width > 1280) and width > height:
			return "FHD"

		if (height == 720 or width == 1280) and width > height:
			return "HD"
		return "SD"

	def constructVideoLabel(self):
		source = self.item.get("MediaSources", [{}])[0]
		streams = source.get("MediaStreams", [])
		vtrack = next((v_track for v_track in streams if v_track.get("Type") == "Video"), None)
		return vtrack.get("DisplayTitle", "").split(" (")[0].upper() if vtrack else ""

	def constructAudioLabel(self):
		source = self.item.get("MediaSources", [{}])[0]
		streams = source.get("MediaStreams", [])
		atrack = streams[self.curAtrackIndex]
		return atrack.get("DisplayTitle", "").split(" (")[0]

	def constructSubtitleLabel(self):
		if not self.curSubsIndex or self.curSubsIndex < 0:
			return ""
		source = self.item.get("MediaSources", [{}])[0]
		streams = source.get("MediaStreams", [])
		strack = next((sub for sub in streams if sub.get("Type") == "Subtitle" and sub.get("Index") == self.curSubsIndex), {})
		return strack.get("DisplayTitle", "")

	def buildEntry(self, item):
		xPos = self.instance.size().width()
		yPos = 0
		height = self.instance.size().height()
		res = [None]

		title = self.getTitle()

		if not self.is_trailer:
			mpaa = item.get("OfficialRating", None)
			resString = self.constructVideoLabel()
			alabel = self.constructAudioLabel()
			slabel = self.constructSubtitleLabel()

			if resString:
				xPos -= 20
				xPos = self.constructLabelBox(res, "VIDEO  ", resString, height, xPos, yPos)

			if alabel:
				xPos = self.constructLabelBox(res, "AUDIO  ", alabel, height, xPos, yPos)

			if slabel:
				xPos = self.constructLabelBox(res, "CC  ", slabel, height, xPos, yPos)

			if mpaa:
				xPos = self.constructLabelBox(res, None, mpaa, height, xPos, yPos)

		res.append(MultiContentEntryText(
			pos=(0, 0), size=(xPos - 35, height),
			font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER | RT_BLEND | RT_ELLIPSIS,
			text=title,
			color=0xffffff, color_sel=0xffffff))

		return res
