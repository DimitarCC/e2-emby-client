from twisted.internet import threads

from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.Progress import Progress
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

from . import _
from .EmbyInfoLine import EmbyInfoLine
from .EmbyItemFunctionButtons import EmbyItemFunctionButtons
from .EmbyRestClient import EmbyApiClient
from .Variables import plugin_dir

UP_NEXT_COUNTDOWN_SECONDS = 30


class EmbyUpNextScreen(Screen):
	skin = ["""<screen name="EmbyUpNextScreen" position="fill" flags="wfNoBorder" zPosition="1000" backgroundColor="#FF000000">
					<eLabel backgroundColor="#20111111" position="60,60" zPosition="-1" size="e-120,470" cornerRadius="10" widgetBorderWidth="1" widgetBorderColor="#444444"/>
					<widget name="thumb" position="90,90" size="480,270" zPosition="1" cornerRadius="6" scale="1" alphatest="blend"/>
					<widget name="title" position="600,90" size="e-660,60" font="Bold;34" transparent="1" noWrap="1"/>
					<widget name="info_panel_line" position="600,150" size="e-660,45" font="Bold;28" fontAdditional="Bold;24" transparent="1"/>
					<widget name="plot" position="600,205" size="e-660,140" font="Regular;26" transparent="1"/>
					<widget name="countdown_label" position="600,355" size="400,35" font="Regular;26" transparent="1" foregroundColor="#ffffff"/>
					<widget source="countdown_progress" render="Progress" position="600,395" size="e-660,10" backgroundColor="#02333333" foregroundColor="#32772b" cornerRadius="4" transparent="1"/>
					<widget name="function_buttons" position="90,380" size="480,80" font="Regular;28" transparent="1"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session):
		Screen.__init__(self, session)
		self["thumb"] = Pixmap()
		self["title"] = Label()
		self["info_panel_line"] = EmbyInfoLine(self)
		self["plot"] = Label()
		self["countdown_label"] = Label()
		self["countdown_progress"] = Progress()
		self["countdown_progress"].value = 0
		self["function_buttons"] = EmbyItemFunctionButtons(self)
		self.cancelIcon = LoadPixmap("%s/cancel.png" % plugin_dir)

	def updateInfo(self, item):
		title = " ".join(item.get("Name", "").splitlines())
		season = item.get("ParentIndexNumber")
		episode = item.get("IndexNumber")
		if season is not None and episode is not None:
			title = f"S{season}:E{episode} - {title}"
		self["title"].setText(title)
		self["info_panel_line"].updateInfo(item)
		self["plot"].setText(item.get("Overview", ""))
		self["thumb"].setPixmap(None)

	def updateThumbnail(self, pixmap):
		if pixmap:
			self["thumb"].setPixmap(pixmap)

	def updateCountdown(self, seconds_left):
		self["countdown_label"].setText(_("Playing next in %d s") % seconds_left)
		self["countdown_progress"].value = int(((UP_NEXT_COUNTDOWN_SECONDS - seconds_left) / float(UP_NEXT_COUNTDOWN_SECONDS)) * 100)

	def setButtons(self, play_callback, cancel_callback):
		buttons_widget = self["function_buttons"]
		buttons_widget.buttons = [
			(0, buttons_widget.playIcon, _("Play Now"), play_callback),
			(1, self.cancelIcon, _("Cancel"), cancel_callback),
		]
		buttons_widget.playButtonIndex = 0
		buttons_widget.focusButton(0)


upNextScreenPopup = None


def loadUpNextThumbnail(item):
	item_id = item.get("Id")
	icon_tag = item.get("ImageTags", {}).get("Primary")
	if not item_id or not icon_tag:
		return None
	path = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_tag, width=480, height=270, image_type="Primary")
	return LoadPixmap(path) if path else None


def onUpNextThumbnailLoaded(pixmap):
	if upNextScreenPopup and pixmap:
		upNextScreenPopup.updateThumbnail(pixmap)


def showUpNextScreen(session, item, play_callback, cancel_callback):
	global upNextScreenPopup
	if not upNextScreenPopup and session:
		upNextScreenPopup = session.instantiateDialog(EmbyUpNextScreen)
	if upNextScreenPopup:
		upNextScreenPopup.updateInfo(item)
		upNextScreenPopup.setButtons(play_callback, cancel_callback)
		upNextScreenPopup.updateCountdown(UP_NEXT_COUNTDOWN_SECONDS)
		upNextScreenPopup.show()
		threads.deferToThread(loadUpNextThumbnail, item).addCallback(onUpNextThumbnailLoaded)


def updateUpNextCountdown(seconds_left):
	if upNextScreenPopup:
		upNextScreenPopup.updateCountdown(seconds_left)


def moveUpNextSelectionLeft():
	if upNextScreenPopup:
		upNextScreenPopup["function_buttons"].movePrevious()


def moveUpNextSelectionRight():
	if upNextScreenPopup:
		upNextScreenPopup["function_buttons"].moveNext()


def activateUpNextSelectedButton():
	if upNextScreenPopup:
		selected = upNextScreenPopup["function_buttons"].getSelectedButton()
		if selected:
			selected[3]()


def hideUpNextScreen():
	if upNextScreenPopup:
		upNextScreenPopup.hide()
