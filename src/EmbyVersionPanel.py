from enigma import eListbox, eListboxPythonMultiContent, eSize, gFont, RT_VALIGN_CENTER, RT_HALIGN_LEFT, RT_BLEND, BT_SCALE, BT_KEEP_ASPECT_RATIO
from skin import parseFont

from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryRectangle
from Tools.LoadPixmap import LoadPixmap

from .Variables import plugin_dir
from . import _


def formatMediaSourceLabel(media_source):
	name = media_source.get("Name") or (media_source.get("Container") or "").upper() or _("Version")
	video_stream = next((s for s in media_source.get("MediaStreams", []) if s.get("Type") == "Video"), None)
	details = []
	if video_stream:
		resolution = describeResolution(video_stream)
		if resolution:
			details.append(resolution)
		codec = video_stream.get("Codec")
		if codec:
			details.append(codec.upper())
	size = media_source.get("Size")
	if size:
		details.append(formatFileSize(size))
	if details:
		return f"{name} ({', '.join(details)})"
	return name


def describeResolution(video_stream):
	width = video_stream.get("Width")
	height = video_stream.get("Height")
	if not width and not height:
		return None
	# Classify by width: ultra-wide/cropped sources (e.g. 1280x694 for a
	# 2.35:1 720p movie) report a shorter height than the nominal bucket,
	# but the width still matches the source's real resolution class.
	if width:
		if width >= 3800:
			return "4K"
		if width >= 1900:
			return "1080p"
		if width >= 1280:
			return "720p"
	if height:
		return f"{height}p"
	return None


def formatFileSize(size_bytes):
	size = float(size_bytes)
	for unit in ("B", "KB", "MB", "GB", "TB"):
		if size < 1024:
			return f"{size:.1f}{unit}"
		size /= 1024
	return f"{size:.1f}PB"


class EmbyVersionPanel(GUIComponent):
	def __init__(self, screen):
		GUIComponent.__init__(self)
		self.screen = screen
		self.entries = []
		self.cursorIndex = 0
		self.selectionEnabled = True
		self.selectedMediaSourceId = None
		self.rowHeight = 72
		self.maxHeight = 0
		self.panelWidth = 0
		self.font = gFont("Regular", 24)
		self.checkIcon = LoadPixmap("%s/check_24.png" % plugin_dir)
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.l.setOrientation(eListbox.orVertical)

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setSelectionEnable(False)
		instance.setContent(self.l)
		instance.hide()

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value) in self.skinAttributes[:]:
			if attrib == "font":
				self.font = parseFont(value, parent.scale)
			elif attrib == "rowHeight":
				self.rowHeight = int(value)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		res = GUIComponent.applySkin(self, desktop, parent)
		self.l.setItemHeight(self.rowHeight)
		self.maxHeight = self.instance.size().height()
		self.panelWidth = self.instance.size().width()
		return res

	def toggleSelection(self, enabled):
		self.selectionEnabled = enabled

	def loadVersions(self, media_sources, selectedMediaSourceId):
		self.entries = media_sources
		self.selectedMediaSourceId = selectedMediaSourceId or (media_sources[0].get("Id") if media_sources else None)
		self.cursorIndex = next((i for i, ms in enumerate(media_sources) if ms.get("Id") == self.selectedMediaSourceId), 0)
		self.resizeToContent()
		self.refresh()

	def resizeToContent(self):
		if not self.instance or not self.maxHeight:
			return
		max_visible = max(1, self.maxHeight // self.rowHeight)
		visible_count = max(1, min(len(self.entries), max_visible))
		self.instance.resize(eSize(self.panelWidth, visible_count * self.rowHeight))

	def refresh(self):
		self.l.setList([(i, ms) for i, ms in enumerate(self.entries)])
		if self.instance:
			self.instance.moveSelectionTo(self.cursorIndex)
		if self.screen:
			# the listbox redraw can repaint over the panel header; force a
			# hide/show cycle (a plain .show() on an already-shown widget is
			# a no-op) so it gets re-raised above the panel background
			title = self.screen["version_panel_title"]
			title.hide()
			title.show()

	def moveUp(self):
		if self.cursorIndex > 0:
			self.cursorIndex -= 1
			self.refresh()

	def moveDown(self):
		if self.cursorIndex < len(self.entries) - 1:
			self.cursorIndex += 1
			self.refresh()

	def getSelectedMediaSource(self):
		if 0 <= self.cursorIndex < len(self.entries):
			return self.entries[self.cursorIndex]
		return None

	def buildEntry(self, index, media_source):
		res = [None]
		selected = index == self.cursorIndex
		is_current = media_source.get("Id") == self.selectedMediaSourceId
		back_color = 0x32772b if selected else 0x222222
		border_color = 0x32772b if selected else 0x404040
		width = self.instance.size().width()

		res.append(MultiContentEntryRectangle(
			pos=(4, 3), size=(width - 8, self.rowHeight - 6),
			cornerRadius=8,
			borderWidth=2, borderColor=border_color,
			backgroundColor=back_color, backgroundColorSelected=back_color))

		text_x = 24
		if is_current:
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(16, (self.rowHeight - 24) // 2), size=(24, 24),
				png=self.checkIcon,
				backcolor=None, backcolor_sel=None,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
			text_x = 52

		res.append(MultiContentEntryText(
			pos=(text_x, 0), size=(width - text_x - 20, self.rowHeight),
			font=0, flags=RT_HALIGN_LEFT | RT_BLEND | RT_VALIGN_CENTER,
			text=formatMediaSourceLabel(media_source),
			color=0xffffff, color_sel=0xffffff))
		return res
