from enigma import eTimer
from Components.config import config
from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

from . import _, Globals
from .Variables import plugin_dir


notificationPopup = None
onNotificationRequested = []
notifications = []


class EmbyNotification(Screen):
	skin = ["""<screen name="EmbyNotification" position="0,e-50" size="e,50" flags="wfNoBorder" zPosition="100" backgroundColor="#00111111">
		 			<widget name="icon" position="10,9" size="32,32" alphatest="blend" zPosition="10"/>
					<widget name="text" position="60,0" size="e-60-10-32-10,50" alphatest="blend" font="Bold;40" halign="center" valign="center" transparent="1"/>
		 			<widget name="icon2" position="e-10-32,9" size="32,32" alphatest="blend" zPosition="10"/>
				</screen>"""]  # noqa: E124

	EMBY_NOTIFICATION_TYPE_INFO = 0
	EMBY_NOTIFICATION_TYPE_WARNING = 1
	EMBY_NOTIFICATION_TYPE_ERROR = 2

	def __init__(self, session, text, type, timeout):
		Screen.__init__(self, session)
		self.type = type
		self.autocloseTimer = eTimer()
		self.autocloseTimer.callback.append(self.closeNotificationPopup)
		self.infoIcon = LoadPixmap("%s/notify_info.png" % plugin_dir)
		self.warningIcon = LoadPixmap("%s/notify_warning.png" % plugin_dir)
		self.errorIcon = LoadPixmap("%s/notify_error.png" % plugin_dir)
		self["text"] = Label(text=text)
		self["icon"] = Pixmap()
		self["icon2"] = Pixmap()
		self.onLayoutFinish.append(self.__onLayoutFinished)
		if timeout > -1:
			self.autocloseTimer.start(timeout, True)

	def closeNotificationPopup(self):
		global notificationPopup
		self.hide()
		notificationPopup = None

	def __onLayoutFinished(self):
		match self.type:
			case self.EMBY_NOTIFICATION_TYPE_INFO:
				self["icon"].setPixmap(self.infoIcon)
				self["icon2"].setPixmap(self.infoIcon)
			case self.EMBY_NOTIFICATION_TYPE_WARNING:
				self["icon"].setPixmap(self.warningIcon)
				self["icon2"].setPixmap(self.warningIcon)
			case self.EMBY_NOTIFICATION_TYPE_ERROR:
				self["icon"].setPixmap(self.errorIcon)
				self["icon2"].setPixmap(self.errorIcon)


class NotificationalScreen(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		if self.onNotificationRequested not in onNotificationRequested:
			onNotificationRequested.append(self.onNotificationRequested)
		self.onClose.append(self.__onClosed)

	def __onClosed(self):
		if self.onNotificationRequested in onNotificationRequested:
			onNotificationRequested.remove(self.onNotificationRequested)
		global notificationPopup
		if notificationPopup:
			notificationPopup.hide()
			notificationPopup = None

	def onNotificationRequested(self):
		if notifications:
			self.showNotificationDialog(notification=notifications.pop(0))

	def showNotificationDialog(self, notification):
		global notificationPopup
		if not notificationPopup and self.session:
			notificationPopup = self.session.instantiateDialog(EmbyNotification, text=notification[2], type=notification[1], timeout=notification[3])
		notificationPopup.show()


def ShowEmbyTimeoutNotification():
	if Globals.IsPlayingFile:
		return
	exists = any(t[0] == "EmbyTimeout" for t in notifications)
	if not exists:
		notifications.append(("EmbyTimeout", EmbyNotification.EMBY_NOTIFICATION_TYPE_ERROR, _("The connection with server has been lost after %d attempts" % config.plugins.e2embyclient.conretries.value), 5000))
	for x in onNotificationRequested:
		x()
