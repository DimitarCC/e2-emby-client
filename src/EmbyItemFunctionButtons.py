from datetime import datetime, timedelta
import os
from sys import modules
import uuid

from enigma import eServiceReference, eListbox, eListboxPythonMultiContent, BT_SCALE, BT_KEEP_ASPECT_RATIO, gFont, RT_VALIGN_CENTER, RT_HALIGN_LEFT, getDesktop, eSize, RT_BLEND
from skin import parseColor, parseFont


from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryRectangle
from Screens.InfoBar import InfoBar
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_GUISKIN


from .EmbyPlayer import EmbyPlayer
from .EmbyRestClient import EmbyApiClient
from . import _, PluginLanguageDomain


plugin_dir = os.path.dirname(modules[__name__].__file__)


class EmbyItemFunctionButtons(GUIComponent):
	def __init__(self, screen):
		GUIComponent.__init__(self)
		self.screen = screen
		self.buttons = []
		self.selectedIndex = 0
		self.selectionEnabled = True
		self.isMoveLeftRight = False
		self.screen.onShow.append(self.onContainerShown)
		self.data = []
		self.resumeIcon = LoadPixmap("%s/resume.png" % plugin_dir)
		self.playIcon = LoadPixmap("%s/play.png" % plugin_dir)
		self.playStartIcon = LoadPixmap("%s/playstart.png" % plugin_dir)
		self.watchedIcon = LoadPixmap("%s/watched.png" % plugin_dir)
		self.trailerIcon = LoadPixmap("%s/trailer.png" % plugin_dir)
		self.unWatchedIcon = LoadPixmap("%s/unwatched.png" % plugin_dir)
		self.favoriteIcon = LoadPixmap("%s/favorite.png" % plugin_dir)
		self.notFavoriteIcon = LoadPixmap("%s/notfavorite.png" % plugin_dir)
		self.textRenderer = Label("")
		self.font = gFont("Regular", 22)
		self.fontAdditional = gFont("Regular", 22)
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
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		self.l.setFont(0, self.font)
		self.l.setFont(1, self.fontAdditional)
		self.instance.setOrientation(self.orientation)
		self.l.setOrientation(self.orientation)
		return GUIComponent.applySkin(self, desktop, parent)

	def moveSelection(self, dir):
		self.isMoveLeftRight = True
		nextPos = self.selectedIndex + dir
		if nextPos < 0 or nextPos >= len(self.buttons):
			return
		self.selectedIndex = nextPos
		self.updateInfo()

	def moveNext(self):
		self.moveSelection(1)

	def movePrevious(self):
		self.moveSelection(-1)

	def isAtHome(self):
		return self.selectedIndex == 0

	def isAtEnd(self):
		return self.selectedIndex == len(self.buttons) - 1

	def convert_ticks_to_time(self, ticks):
		seconds = ticks / 10_000_000
		minutes = int(seconds // 60)
		hours = int(minutes // 60)
		minutes = minutes % 60
		if hours == 0:
			return f"{minutes}min"
		return f"{hours}h {minutes}min"

	def getSelectedButton(self):
		return self.buttons[self.selectedIndex]

	def playItem(self, startPos=0):
		selected_item = self.item
		infobar = InfoBar.instance
		if infobar:
			LastService = self.screen.session.nav.getCurrentServiceReferenceOriginal()
			item_id = int(selected_item.get("Id", "0"))
			item_name = selected_item.get("Name", "Stream")
			play_session_id = str(uuid.uuid4())
			# subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/mediasource_80606/Subtitles/21/stream.srt?api_key={EmbyApiClient.access_token}"
			url = f"{EmbyApiClient.server_root}/emby/Videos/{item_id}/stream?api_key={EmbyApiClient.access_token}&PlaySessionId={play_session_id}&DeviceId={EmbyApiClient.device_id}&static=true&EnableAutoStreamCopy=false"
			ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % ("4097", item_id, url.replace(":", "%3a"), item_name))
			self.screen.session.open(EmbyPlayer, ref, item=selected_item, play_session_id=play_session_id, startPos=startPos, slist=infobar.servicelist, lastservice=LastService)

	def resumePlay(self):
		startPos = int(self.item.get("UserData", {}).get("PlaybackPositionTicks", "0")) / 10_000_000
		self.playItem(startPos=startPos)

	def playFromBeguinning(self):
		self.playItem()

	def playTrailer(self):
		pass

	def toggleWatched(self):
		pass

	def toggleFavorite(self):
		pass

	def setItem(self, item):
		self.item = item
		type = item.get("Type", None)
		runtime_ticks = int(item.get("RunTimeTicks", "0"))
		position_ticks = int(item.get("UserData", {}).get("PlaybackPositionTicks", "0"))
		trailers = item.get("RemoteTrailers", [])
		played = item.get("UserData", {}).get("Played", False)
		isFavorite = item.get("UserData", {}).get("IsFavorite", False)
		if position_ticks:
			self.buttons.append((len(self.buttons), self.resumeIcon, _("Resume (") + self.convert_ticks_to_time(position_ticks) + ")", self.resumePlay))
			self.buttons.append((len(self.buttons), self.playStartIcon, _("Play from start"), self.playFromBeguinning))
		else:
			self.buttons.append((len(self.buttons), self.playIcon, _("Play"), self.playFromBeguinning))

		if len(trailers) > 0:
			self.buttons.append((len(self.buttons), self.trailerIcon, _("Play trailer"), self.playTrailer))

		self.buttons.append((len(self.buttons), self.watchedIcon if played else self.unWatchedIcon, _("Watched"), self.toggleWatched))

		self.buttons.append((len(self.buttons), self.favoriteIcon if isFavorite else self.notFavoriteIcon, _("Favorite"), self.toggleFavorite))
		self.updateInfo()

	def updateInfo(self):
		l_list = []
		l_list.append((self.buttons,))
		self.l.setList(l_list)

	def enableSelection(self, selection):
		if not selection:
			self.selectedIndex = 0
		self.selectionEnabled = selection
		self.isMoveLeftRight = False
		self.updateInfo()

	def _calcTextSize(self, text, font=None, size=None):
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

	def constructButton(self, res, current_draw_idex, icon, text, height, xPos, yPos, selected=False, spacing=None, backColorSelected=0x32772b, backColor=0x606060, textColor=0xffffff):
		if not spacing:
			spacing = self.spacing

		textWidth = self._calcTextSize(text, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]
		if not selected and (current_draw_idex > 0 or self.isMoveLeftRight):
			textWidth = 0
			text = ""
		rec_height = height
		pixd_width = 0
		pixd_height = 0
		if icon:
			pixd_size = icon.size()
			pixd_width = pixd_size.width()
			pixd_height = pixd_size.height()

		back_color = backColorSelected if selected else backColor
		offset = 0
		res.append(MultiContentEntryRectangle(
				pos=(xPos, yPos), size=(textWidth + pixd_width + (55 if text else 40), rec_height),
				cornerRadius=8,
				backgroundColor=back_color, backgroundColorSelected=back_color))
		offset = xPos + textWidth + pixd_width + (55 if text else 40)

		if icon:
			res.append(MultiContentEntryPixmapAlphaBlend(
				pos=(xPos + 20, yPos + (height - pixd_height) // 2),
				size=(pixd_width, pixd_height),
				png=icon,
				backcolor=None, backcolor_sel=None,
				flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
			xPos += 30 + pixd_width

		if text:
			res.append(MultiContentEntryText(
				pos=(xPos, yPos + (height - rec_height) // 2), size=(textWidth + 16, rec_height),
				font=0, flags=RT_HALIGN_LEFT | RT_BLEND | RT_VALIGN_CENTER,
				text=text,
				color=textColor, color_sel=textColor))
		offset += spacing
		return offset

	def buildEntry(self, buttons):
		xPos = 0
		yPos = 0
		height = self.instance.size().height()
		res = [None]

		for button in buttons:
			selected = button[0] == self.selectedIndex and self.selectionEnabled
			xPos = self.constructButton(res, button[0], button[1], button[2], height, xPos, yPos, selected)

		return res
