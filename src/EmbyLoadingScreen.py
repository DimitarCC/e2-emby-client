from math import cos, radians, sin

from enigma import eTimer

from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

from . import _
from .Variables import EMBY_THUMB_CACHE_DIR

SPINNER_DOT_COUNT = 8
SPINNER_DOT_SIZE = 22
SPINNER_RADIUS = 70
SPINNER_CENTER = (960, 540)
SPINNER_DIM_COLOR = "#444444"
SPINNER_BRIGHT_COLOR = "#32772b"
SPINNER_INTERVAL_MS = 100

loadingScreenPopup = None


def _spinnerDotPosition(index):
	angle = radians(360 * index / SPINNER_DOT_COUNT)
	cx, cy = SPINNER_CENTER
	x = int(cx + SPINNER_RADIUS * cos(angle) - SPINNER_DOT_SIZE / 2)
	y = int(cy + SPINNER_RADIUS * sin(angle) - SPINNER_DOT_SIZE / 2)
	return x, y


def _buildSpinnerSkin():
	parts = []
	for index in range(SPINNER_DOT_COUNT):
		x, y = _spinnerDotPosition(index)
		parts.append(
			f'<eLabel backgroundColor="{SPINNER_DIM_COLOR}" position="{x},{y}" size="{SPINNER_DOT_SIZE},{SPINNER_DOT_SIZE}" '
			f'cornerRadius="{SPINNER_DOT_SIZE // 2}" zPosition="2"/>'
		)
		parts.append(
			f'<widget name="spinner_dot_{index}" backgroundColor="{SPINNER_BRIGHT_COLOR}" position="{x},{y}" size="{SPINNER_DOT_SIZE},{SPINNER_DOT_SIZE}" '
			f'cornerRadius="{SPINNER_DOT_SIZE // 2}" zPosition="3"/>'
		)
	return "".join(parts)


class EmbyLoadingScreen(Screen):
	skin = ["""<screen name="EmbyLoadingScreen" position="fill" flags="wfNoBorder" zPosition="1000" backgroundColor="#ff000000">
					<widget name="backdrop" position="fill" zPosition="1" scale="1"/>
					<eLabel backgroundColor="#80000000" position="fill" zPosition="1"/>
					""" + _buildSpinnerSkin() + """
					<widget name="loading_label" position="810,635" size="300,40" font="Regular;28" halign="center" transparent="1" foregroundColor="#ffffff" zPosition="3"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session):
		Screen.__init__(self, session)
		self["backdrop"] = Pixmap()
		self["loading_label"] = Label()
		for index in range(SPINNER_DOT_COUNT):
			self[f"spinner_dot_{index}"] = Label()
		self.spinnerTimer = eTimer()
		self.spinnerTimer.callback.append(self.__advanceSpinner)
		self.spinnerIndex = 0
		self.spinnerTick = 0
		self.onShow.append(self.__startSpinner)
		self.onHide.append(self.__stopSpinner)

	def updateBackdrop(self):
		self["backdrop"].setPixmap(LoadPixmap(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop_orig.jpg"))

	def __startSpinner(self):
		self.spinnerIndex = 0
		self.spinnerTick = 0
		for index in range(SPINNER_DOT_COUNT):
			self["spinner_dot_%d" % index].hide()
		self.__showSpinnerDot(self.spinnerIndex)
		self["loading_label"].setText(_("Loading") + ".")
		self.spinnerTimer.start(SPINNER_INTERVAL_MS, False)

	def __stopSpinner(self):
		self.spinnerTimer.stop()

	def __advanceSpinner(self):
		self["spinner_dot_%d" % self.spinnerIndex].hide()
		self.spinnerIndex = (self.spinnerIndex + 1) % SPINNER_DOT_COUNT
		self.__showSpinnerDot(self.spinnerIndex)
		self.spinnerTick += 1
		self["loading_label"].setText(_("Loading") + "." * (1 + (self.spinnerTick // 4) % 3))

	def __showSpinnerDot(self, index):
		self["spinner_dot_%d" % index].show()


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
