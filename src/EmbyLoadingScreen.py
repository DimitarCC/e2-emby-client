from Components.Pixmap import Pixmap
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

from .Variables import EMBY_THUMB_CACHE_DIR


loadingScreenPopup = None


class EmbyLoadingScreen(Screen):
	skin = ["""<screen name="EmbyLoadingScreen" position="fill" flags="wfNoBorder" zPosition="1000" backgroundColor="#ff000000">
					<widget name="backdrop" position="fill" zPosition="1" scale="1"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session):
		Screen.__init__(self, session)
		self["backdrop"] = Pixmap()

	def updateBackdrop(self):
		self["backdrop"].setPixmap(LoadPixmap(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop_orig.jpg"))


def showLoadingScreen(session):
	global loadingScreenPopup
	if not loadingScreenPopup and session:
		loadingScreenPopup = session.instantiateDialog(EmbyLoadingScreen)
	if loadingScreenPopup:
		loadingScreenPopup.updateBackdrop()
		loadingScreenPopup.show()


def hideLoadingScreen():
	global loadingScreenPopup
	if loadingScreenPopup:
		loadingScreenPopup.hide()
