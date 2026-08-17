from Components.Label import Label
from Screens.Screen import Screen

from . import _


class EmbySkipIntroScreen(Screen):
	skin = ["""<screen name="EmbySkipIntroScreen" position="fill" flags="wfNoBorder" zPosition="1000" backgroundColor="#FF000000">
					<widget name="skip_intro_button" position="e-450,e-230" size="300,80" backgroundColor="#32772b" foregroundColor="#ffffff" font="Bold;30" halign="center" valign="center" cornerRadius="10" widgetBorderWidth="2" widgetBorderColor="#ffffff"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session):
		Screen.__init__(self, session)
		self["skip_intro_button"] = Label(_("Skip Intro"))


skipIntroScreenPopup = None


def showSkipIntroScreen(session):
	global skipIntroScreenPopup
	if not skipIntroScreenPopup and session:
		skipIntroScreenPopup = session.instantiateDialog(EmbySkipIntroScreen)
	if skipIntroScreenPopup:
		skipIntroScreenPopup.show()


def hideSkipIntroScreen():
	global skipIntroScreenPopup
	if skipIntroScreenPopup:
		skipIntroScreenPopup.hide()
