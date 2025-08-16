from . import _, PluginLanguageDomain

import os
from sys import modules

from enigma import eListbox, eListboxPythonMultiContent, BT_SCALE, BT_KEEP_ASPECT_RATIO, gFont, RT_VALIGN_CENTER, RT_HALIGN_CENTER, getDesktop, eSize, RT_BLEND
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryRectangle
from Tools.Directories import resolveFilename, SCOPE_GUISKIN
from Tools.LoadPixmap import LoadPixmap

from .HelperFunctions import convert_ticks_to_time, embyDateToString, embyEndsAtToString


plugin_dir = os.path.dirname(modules[__name__].__file__)


class EmbyInfoLine(GUIComponent):
	def __init__(self, screen):
		GUIComponent.__init__(self)
		self.screen = screen
		self.screen.onShow.append(self.onContainerShown)
		self.data = []
		self.textRenderer = Label("")
		self.font = gFont("Regular", 18)
		self.fontAdditional = gFont("Regular", 18)
		self.foreColorAdditional = 0xffffff
		self.star24 = LoadPixmap(resolveFilename(SCOPE_GUISKIN, "icons/emby_star.png"))
		if not self.star24:
			self.star24 = LoadPixmap("%s/star.png" % plugin_dir)
		self.rt_gt_60 = LoadPixmap(resolveFilename(SCOPE_GUISKIN, "icons/emby_rtgt60.png"))
		if not self.rt_gt_60:
			self.rt_gt_60 = LoadPixmap("%s/rt60.png" % plugin_dir)
		self.rt_lt_60 = LoadPixmap(resolveFilename(SCOPE_GUISKIN, "icons/emby_rtlt60.png"))
		if not self.rt_lt_60:
			self.rt_lt_60 = LoadPixmap("%s/rt59.png" % plugin_dir)
		self.l = eListboxPythonMultiContent()  # noqa: E741
		self.l.setBuildFunc(self.buildEntry)
		self.spacing = 30
		self.orientations = {"orHorizontal": eListbox.orHorizontal, "orVertical": eListbox.orVertical}
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
		self.textRenderer.GUIcreate(self.screen.instance)

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
			elif attrib == "orientation":
				self.orientation = self.orientations.get(value, self.orientations["orHorizontal"])
				if self.orientation == eListbox.orHorizontal:
					self.instance.setOrientation(eListbox.orVertical)
					self.l.setOrientation(eListbox.orVertical)
				else:
					self.instance.setOrientation(eListbox.orHorizontal)
					self.l.setOrientation(eListbox.orHorizontal)
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.l.setFont(1, self.fontAdditional)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		return GUIComponent.applySkin(self, desktop, parent)

	def updateInfo(self, item):
		l_list = []
		l_list.append((item,))
		self.l.setList(l_list)

	def _calcTextWidth(self, text, font=None, size=None):
		self.textRenderer.instance.setNoWrap(1)
		if size:
			self.textRenderer.instance.resize(size)
		if font:
			self.textRenderer.instance.setFont(font)
		self.textRenderer.text = text
		size = self.textRenderer.instance.calculateSize()
		res_width = size.width()
		res_height = size.height()
		self.textRenderer.text = ""
		return res_width, res_height

	def getDesktopWith(self):
		return getDesktop(0).size().width()

	def getSize(self):
		s = self.instance.size()
		return s.width(), s.height()

	def constructLabelBox(self, res, text, height, xPos, yPos, spacing=None, borderColor=0xadacaa, backColor=0x02111111, textColor=0xffffff):
		if not spacing:
			spacing = self.spacing

		textWidth, textHeight = self._calcTextWidth(text, font=self.fontAdditional, size=eSize(self.getDesktopWith() // 3, 0))
		rec_height = textHeight + 1
		res.append(MultiContentEntryRectangle(
				pos=(xPos, yPos - 1 + (height - rec_height) // 2), size=(textWidth + 20, rec_height),
				cornerRadius=6,
				backgroundColor=borderColor, backgroundColorSelected=borderColor))
		res.append(MultiContentEntryRectangle(
				pos=(xPos + 2, yPos - 1 + (height - rec_height) // 2 + 2), size=(textWidth + 16, rec_height - 4),
				cornerRadius=4,
				backgroundColor=backColor, backgroundColorSelected=backColor))

		res.append(MultiContentEntryText(
			pos=(xPos + 2, yPos - 2 + (height - rec_height) // 2 + 2), size=(textWidth + 16, rec_height - 4),
			font=1, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
			text=text,
			color=textColor, color_sel=textColor))
		xPos += spacing + textWidth + 20
		return xPos

	def constructResolutionLabel(self, width, height):
		if width == 0 or height == 0:
			return ""

		if height > 1080 and width > 1920:
			return "UHD"

		if height > 720 and width > 1280:
			return "FHD"

		if height == 720 and width == 1280:
			return "HD"
		return "SD"

	def constructAudioLabel(self, streams):
		dts_list = list(filter(lambda track: track.get("Codec") == "dts", streams))

		if dts_list:
			sorted_dts_list = sorted(dts_list, key=lambda track: track.get("ChannelLayout"))
			dts_track = sorted_dts_list[-1]
			return dts_track.get("Profile"), dts_track.get("ChannelLayout")

		dolby_list = list(filter(lambda track: track.get("Codec") in ["eac3", "ac3"], streams))

		if dolby_list:
			sorted_dolby_list = sorted(dolby_list, key=lambda track: track.get("ChannelLayout"))
			dolby_track = sorted_dolby_list[-1]
			return "DOLBY", dolby_track.get("ChannelLayout", "").replace("stereo", "2.0")
		return None, None

	def buildEntry(self, item):
		xPos = 0
		yPos = 0
		height = self.instance.size().height()
		res = [None]

		type = item.get("Type", None)

		premiereDate_str = item.get("PremiereDate", None)
		premiereDate = premiereDate_str and embyDateToString(premiereDate_str, type)
		user_rating = int(item.get("CommunityRating", "0"))
		critics_rating = int(item.get("CriticRating", "0"))
		mpaa = item.get("OfficialRating", None)
		runtime_ticks = int(item.get("RunTimeTicks", "0"))
		runtime = runtime_ticks and convert_ticks_to_time(runtime_ticks)
		position_ticks = int(item.get("UserData", {}).get("PlaybackPositionTicks", "0"))
		ends_at = embyEndsAtToString(runtime_ticks, position_ticks)
		v_width = int(item.get("Width", "0"))
		v_height = int(item.get("Height", "0"))
		resString = self.constructResolutionLabel(v_width, v_height)
		streams = item.get("MediaSources", [{}])[0].get("MediaStreams", [])

		audioCodec, audioCh = self.constructAudioLabel(streams)

		has_subtitles = any(stream.get("Type") == "Subtitle" for stream in streams)

		if user_rating:
			pixd_size = self.star24.size()
			pixd_width = pixd_size.width()
			pixd_height = pixd_size.height()
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(xPos, yPos - 2 + (height - pixd_height) // 2),
				size=(pixd_width, height),
				png=self.star24,
				backcolor=None, backcolor_sel=None,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
			xPos += 7 + pixd_width

			user_rating_str = f" {user_rating:.1f}"

			textWidth = self._calcTextWidth(user_rating_str, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

			res.append(MultiContentEntryText(
				pos=(xPos, yPos), size=(textWidth, height),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=user_rating_str,
				color=0xffffff, color_sel=0xffffff))
			xPos += self.spacing + textWidth

		if critics_rating:
			rt_icon = self.rt_gt_60
			if critics_rating < 60:
				rt_icon = self.rt_lt_60
			pixd_size = rt_icon.size()
			pixd_width = pixd_size.width()
			pixd_height = pixd_size.height()
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(xPos, yPos - 2 + (height - pixd_height) // 2),
				size=(pixd_width, height),
				png=rt_icon,
				backcolor=None, backcolor_sel=None,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
			xPos += 7 + pixd_width

			critics_rating_str = f" {critics_rating}%"

			textWidth = self._calcTextWidth(critics_rating_str, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

			res.append(MultiContentEntryText(
				pos=(xPos, yPos), size=(textWidth, height),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=critics_rating_str,
				color=0xffffff, color_sel=0xffffff))
			xPos += self.spacing + textWidth

		if premiereDate:
			textWidth = self._calcTextWidth(premiereDate, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

			res.append(MultiContentEntryText(
				pos=(xPos, yPos), size=(textWidth, height),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=premiereDate,
				color=0xffffff, color_sel=0xffffff))
			xPos += self.spacing + textWidth

		if runtime:
			textWidth = self._calcTextWidth(runtime, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

			res.append(MultiContentEntryText(
				pos=(xPos, yPos), size=(textWidth, height),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=runtime,
				color=0xffffff, color_sel=0xffffff))
			xPos += self.spacing + textWidth

		if mpaa:
			xPos = self.constructLabelBox(res, mpaa, height, xPos, yPos, 10 if resString or audioCodec or audioCh or has_subtitles else None)

		if resString:
			xPos = self.constructLabelBox(res, resString, height, xPos, yPos, 10 if audioCodec or audioCh or has_subtitles else None)

		if audioCodec:
			xPos = self.constructLabelBox(res, audioCodec, height, xPos, yPos, 10 if audioCh or has_subtitles else None)

		if audioCh:
			xPos = self.constructLabelBox(res, audioCh, height, xPos, yPos, 10 if has_subtitles else None)

		if has_subtitles:
			xPos = self.constructLabelBox(res, "CC", height, xPos, yPos)

		if ends_at:
			textWidth = self._calcTextWidth(ends_at, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

			res.append(MultiContentEntryText(
				pos=(xPos, yPos), size=(textWidth, height),
				font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
				text=ends_at,
				color=0xffffff, color_sel=0xffffff))
			xPos += self.spacing + textWidth

		return res
