from os.path import join
from pathlib import Path
from time import sleep
from twisted.internet import threads
from PIL import Image

from enigma import eTimer, iPlayableService, ePoint

from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.config import config
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Screens.Screen import Screen, ScreenSummary
from Tools.Directories import resolveFilename, SCOPE_GUISKIN
from Tools.LoadPixmap import LoadPixmap

from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyInfoLine import EmbyInfoLine
from .EmbyItemFunctionButtons import EmbyItemFunctionButtons, playItem
from .EmbySetup import getActiveConnection, EmbySetup
from .EmbyRestClient import EmbyApiClient, DIRECTORY_PARSER
from .EmbyLibraryScreen import E2EmbyLibrary
from .EmbyMovieItemView import EmbyMovieItemView
from .EmbyNotification import NotificationalScreen
from .EmbyEpisodeItemView import EmbyEpisodeItemView
from .EmbyBoxSetItemView import EmbyBoxSetItemView
from .EmbySeriesItemView import EmbySeriesItemView
from .EmbyItemViewBase import EXIT_RESULT_MOVIE, EXIT_RESULT_SERIES, EXIT_RESULT_EPISODE
from .EmbyLoadingScreen import showLoadingScreen
from .HelperFunctions import create_thumb_cache_dir, delete_thumb_cache_dir
from .Variables import plugin_dir, EMBY_THUMB_CACHE_DIR, EMBY_ACCENT_GREEN_RGB
from . import _

current_thread = None


class _ServiceRestorer:
	# Navigation's own "tuner still releasing from a just-stopped stream" retry
	# only arms when the previous service reference still has "://" in it at
	# the moment playService() is called - which isn't the case here, since the
	# service has been sitting stopped for as long as the plugin was open. So
	# retry the restore ourselves a few times, mirroring Navigation's own
	# cadence/window, in case the tuner hasn't fully released yet.
	#
	# getCurrentlyPlayingServiceReference() flips to non-None as soon as
	# playService() is issued, regardless of whether the tune actually took -
	# while the tuner is still releasing, Navigation can silently fail to
	# start the service while still recording it as "current". So it can't be
	# used to decide when to stop retrying; keep reissuing playService() on
	# the same cadence (it's a cheap no-op once the service is genuinely
	# already playing) until evStart arrives or attempts run out, then give
	# evStart one last window before giving up and closing anyway.
	MAX_ATTEMPTS = 14
	RETRY_DELAY = 700  # ms
	START_TIMEOUT = 3000  # ms

	def __init__(self, session, ref, on_done):
		self.session = session
		self.ref = ref
		self.on_done = on_done
		self.attempts = 0
		self.finished = False
		self.timer = eTimer()
		self.timer.callback.append(self.__attempt)
		self.session.nav.event.append(self.__onServiceEvent)
		self.timer.start(300, True)

	def __attempt(self):
		self.attempts += 1
		self.session.nav.playService(self.ref)
		if self.attempts < self.MAX_ATTEMPTS:
			self.timer.start(self.RETRY_DELAY, True)
		else:
			self.timer.start(self.START_TIMEOUT, True)

	def __onServiceEvent(self, ev):
		# evVideoSizeChanged only fires when the decoded resolution actually
		# changes, so it can't be relied on alone - a restored service with
		# the same resolution as whatever was last on screen would never
		# trigger it, leaving evUpdatedInfo as the only reliable signal.
		if ev in (iPlayableService.evUpdatedInfo, iPlayableService.evVideoSizeChanged):
			self.__finish()

	def __finish(self):
		if self.finished:
			return
		self.finished = True
		self.timer.stop()
		self.session.nav.event.remove(self.__onServiceEvent)
		self.on_done()


class E2EmbyHome(NotificationalScreen):
	skin = ["""<screen name="E2EmbyHome" position="fill">
				<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
				<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget name="premiere_badge" position="e-340,30" size="50,50" alphatest="blend" zPosition="20"/>
				<widget name="avatar" position="e-270,25" size="60,60" alphatest="blend" zPosition="20"/>
				<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-3" scaleFlags="moveRightTop"/>
				<widget name="title_logo" position="60,140" size="924,80" alphatest="blend"/>
				<widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
				<widget name="subtitle" position="60,235" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
				<widget name="infoline" position="60,240" size="e-120,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
				<widget name="plot" position="60,310" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
				<widget name="f_buttons" position="60,485" size="924,65" font="Regular;32" transparent="1"/>
				<widget name="list_header" position="55,570" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
				<widget name="list_watching_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
				<widget name="list_recent_movies_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
				<widget name="list" position="40,620" size="e-80,230" scrollbarMode="showNever" transparent="1" />
				<widget name="list_watching" position="35,820" size="e-80,270" iconWidth="338" iconHeight="192" scrollbarMode="showNever" iconType="Thumb" transparent="1" />
				<widget name="list_recent_movies" position="35,1150" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
				<widget name="list_recent_tvshows_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
				<widget name="list_recent_tvshows" position="35,1600" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
			</screen>"""]

	def __init__(self, session, stopped_service_ref=None):
		NotificationalScreen.__init__(self, session)
		self.setTitle(_("Emby"))

		self.stopped_service_ref = stopped_service_ref
		self.restoring_service = False
		self.access_token = None
		self.home_loaded = False
		self.loaded_connection = None
		self.last_item_id = None
		self.last_widget_info_load_success = None
		self.processing_cover = False
		self.deferred_cover_url = None
		self.deferred_image_tag = None
		self.last_cover = ""
		self.backdrop_pix = None
		self.logo_pix = None

		self.plot_posy_orig = 310
		self.plot_height_orig = 168
		self.plot_width_orig = 924

		self.f_buttons_focused = False
		self.f_buttons_visible = False
		self.info_display_item = None

		self.mask_alpha = Image.open(join(
			plugin_dir, "mask_l.png")).convert("RGBA").split()[3]
		if self.mask_alpha.mode != "L":
			self.mask_alpha = self.mask_alpha.convert("L")

		self.availableWidgets = ["list"]
		self.selected_widget = "list"

		self.top_slot_y = 570

		self.onShown.append(self.__onShown)
		self.onClose.append(self.__onClose)
		self.onLayoutFinish.append(self.__onLayoutFinished)
		self.sel_timer = eTimer()
		self.sel_timer.callback.append(self.trigger_sel_changed_event)

		self.movie_libs_ids = []
		self.tvshow_libs_ids = []
		self.music_libs_ids = []

		self["title_logo"] = Pixmap()
		self["title"] = Label()
		self["subtitle"] = Label()
		self["infoline"] = EmbyInfoLine(self)
		self["plot"] = Label()
		self["f_buttons"] = EmbyItemFunctionButtons(self)
		self["f_buttons"].onPlayerExit.append(self.playerExitCallback)
		self["backdrop"] = Pixmap()
		self["avatar"] = Pixmap()
		self["avatar"].hide()
		self["premiere_badge"] = Pixmap()
		self["premiere_badge"].hide()
		self["list_header"] = Label(_("My Media"))
		self["list"] = EmbyList(isLibrary=True)
		self["list_watching_header"] = Label(_("Continue watching"))
		self["list_watching"] = EmbyList()
		self["list_recent_movies_header"] = Label(_("Recently added movies"))
		self["list_recent_movies"] = EmbyList()
		self["list_recent_tvshows_header"] = Label(_("Recently added tvshows"))
		self["list_recent_tvshows"] = EmbyList()
		self["key_red"] = StaticText(_("Close"))
		# self["key_green"] = StaticText(_("Add provider"))
		# self["key_yellow"] = StaticText(_("Generate bouquets"))
		# self["key_blue"] = StaticText(_("Clear all data"))
		# self["key_info"] = StaticText()
		# self["description"] = StaticText(
		# 	_("Press OK to edit the currently selected provider"))

		self.lists = {}
		self.lists["list"] = EmbyListController(
			self["list"], self["list_header"])
		self.lists["list_watching"] = EmbyListController(
			self["list_watching"], self["list_watching_header"])
		self.lists["list_recent_movies"] = EmbyListController(
			self["list_recent_movies"], self["list_recent_movies_header"])
		self.lists["list_recent_tvshows"] = EmbyListController(
			self["list_recent_tvshows"], self["list_recent_tvshows_header"])

		self["list"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_watching"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recent_movies"].onSelectionChanged.append(self.onSelectedIndexChanged)
		self["list_recent_tvshows"].onSelectionChanged.append(self.onSelectedIndexChanged)

		self["actions"] = ActionMap(["E2EmbyActions",],
									{
			"cancel": self.cancel,  # KEY_RED / KEY_EXIT
			# "save": self.addProvider,  # KEY_GREEN
			"ok": self.processItem,
			"menu": self.menu  # KEY_MENU
			# "yellow": self.keyYellow,
			# "blue": self.clearData,
		}, -1)

		self["nav_actions"] = ActionMap(["NavigationActions",],
										{
			"up": self.up,
			"down": self.down,
			"left": self.left,
			"right": self.right,
			# "blue": self.clearData,
		}, -2)

		# self["infoActions"] = ActionMap(["E2EmbyActions",],
		# 	{
		# 		"info": self.info,
		# 	}, -1)

	def __onLayoutFinished(self):
		self.top_slot_y = self["list_header"].instance.position().y()
		self.plot_posy_orig = self["plot"].instance.position().y()
		plot_size = self["plot"].instance.size()
		self["plot"].setText(" \n" * 3)
		self.plot_height_orig = self["plot"].getSize()[1]
		self.plot_width_orig = plot_size.width()
		self["plot"].resize(plot_size.width(), self.plot_height_orig)
		self["f_buttons"].instance.hide()

	def __onShown(self):
		activeConnection = getActiveConnection()
		self.lists["list_watching"].enableSelection(self.selected_widget == "list_watching")
		self.lists["list_recent_movies"].enableSelection(self.selected_widget == "list_recent_movies")
		self.lists["list_recent_tvshows"].enableSelection(self.selected_widget == "list_recent_tvshows")
		if self.home_loaded and activeConnection != self.loaded_connection:
			self.home_loaded = False
		if not self.home_loaded:
			self.movie_libs_ids = []
			self.tvshow_libs_ids = []
			self.music_libs_ids = []
			self.availableWidgets = ["list"]
			self.last_item_id = None
			self.last_widget_info_load_success = None
			self.clearInfoPane()
			self["avatar"].hide()
			self["premiere_badge"].hide()
			self.lists["list_watching"].visible(False)
			self.lists["list_recent_movies"].visible(False)
			self.lists["list_recent_tvshows"].visible(False)
			threads.deferToThread(self.loadHome, activeConnection)

	def trigger_sel_changed_event(self):
		threads.deferToThread(self.loadSelectedItemDetails, self[self.selected_widget].selectedItem, self[self.selected_widget])

	def onSelectedIndexChanged(self, widget=None, item_id=None):
		self.last_item_id = self[self.selected_widget].selectedItem.get("Id")
		if (self.last_widget_info_load_success and self.last_widget_info_load_success == widget):
			return

		if not item_id:
			item_id = self[self.selected_widget].selectedItem.get("Id")

		self.sel_timer.stop()
		self.sel_timer.start(config.plugins.e2embyclient.changedelay.value, True)

	def left(self):
		if self.f_buttons_focused:
			self["f_buttons"].movePrevious()
			return
		self.last_widget_info_load_success = None
		if self.selected_widget == "list" and self[self.selected_widget].selectedIndex > 0:
			self.clearInfoPane()

		if self[self.selected_widget].selectedIndex > 0:
			self.backdrop_pix = None
			self["backdrop"].setPixmap(None)
		self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveLeft)

	def right(self):
		if self.f_buttons_focused:
			self["f_buttons"].moveNext()
			return
		self.last_widget_info_load_success = None
		if self.selected_widget == "list" and self[self.selected_widget].selectedIndex < len(self[self.selected_widget].data) - 1:
			self.clearInfoPane()

		if self[self.selected_widget].selectedIndex < len(self[self.selected_widget].data) - 1:
			self.backdrop_pix = None
			self["backdrop"].setPixmap(None)
		self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveRight)

	def up(self):
		if self.f_buttons_focused:
			return
		current_widget_index = self.availableWidgets.index(self.selected_widget)
		if current_widget_index == 0:
			if self.f_buttons_visible:
				self.f_buttons_focused = True
				self.lists[self.selected_widget].enableSelection(False)
				self["f_buttons"].enableSelection(True)
			return
		y = self.top_slot_y

		prevWidgetName = self.availableWidgets[current_widget_index - 1]
		prevItem = self.lists[prevWidgetName]
		prevItem.move(40, y).visible(True).enableSelection(True)
		y += prevItem.getHeight() + 40
		self.selected_widget = prevWidgetName

		for item in self.availableWidgets[current_widget_index:]:
			self.lists[item].move(40, y).enableSelection(False)
			y += self.lists[item].getHeight() + 40

		if self[self.selected_widget].isLibrary:
			self.last_widget_info_load_success = None
			self.clearInfoPane()

		self.backdrop_pix = None
		self["backdrop"].setPixmap(None)

		self.onSelectedIndexChanged()

	def down(self):
		if self.f_buttons_focused:
			self.f_buttons_focused = False
			self["f_buttons"].enableSelection(False)
			self.lists[self.selected_widget].enableSelection(True)
			return
		current_widget_index = self.availableWidgets.index(
			self.selected_widget)
		if current_widget_index == len(self.availableWidgets) - 1:
			return

		safe_index = min(current_widget_index + 1, len(self.availableWidgets))
		for item in self.availableWidgets[:safe_index]:
			self.lists[item].visible(False).enableSelection(False)

		y = self.top_slot_y
		selEnabled = True
		for item in self.availableWidgets[safe_index:]:
			self.lists[item].move(40, y).enableSelection(selEnabled)
			y += self.lists[item].getHeight() + 40
			if selEnabled:
				self.selected_widget = item
			selEnabled = False

		self.backdrop_pix = None
		self["backdrop"].setPixmap(None)
		self.onSelectedIndexChanged()

	def cancel(self):
		if self.restoring_service:
			# Restoration is already in flight from an earlier press - it'll
			# close us once the service comes up, so ignore repeat presses
			# instead of racing multiple restorers/close() calls against
			# each other.
			return
		if self.stopped_service_ref is not None:
			self.restoring_service = True
			_ServiceRestorer(self.session, self.stopped_service_ref, self.close)
		else:
			self.close()

	def processItem(self):
		if self.f_buttons_focused:
			self["f_buttons"].getSelectedButton()[3]()
			return
		widget = self[self.selected_widget]
		selected_item = widget.getCurrentItem()
		if widget.isLibrary:
			self.session.openWithCallback(self.exitCallback, E2EmbyLibrary, selected_item)
		else:
			self.openItemView(selected_item)

	def openItemView(self, selected_item):
		item_type = selected_item.get("Type")
		embyScreenClass = EmbyMovieItemView
		if item_type == "Episode":
			embyScreenClass = EmbyEpisodeItemView
		elif item_type == "BoxSet":
			embyScreenClass = EmbyBoxSetItemView
		elif item_type == "Series":
			embyScreenClass = EmbySeriesItemView
		self.session.openWithCallback(self.exitCallback, embyScreenClass, selected_item, self.backdrop_pix, self.logo_pix)

	def openMoreInfo(self):
		if self.info_display_item:
			self.openItemView(self.info_display_item)

	def playCurrentItem(self):
		if not self.info_display_item:
			return
		item = self.info_display_item
		if item.get("Type") == "Series":
			threads.deferToThread(self.resolvePlayableEpisodeAndPlay, item)
		else:
			self.startPlayback(item)

	def resolvePlayableEpisodeAndPlay(self, series_item):
		series_id = series_item.get("Id")
		resume_episode = EmbyApiClient.getResumeEpisodeForSeries(series_id)
		play_item = resume_episode[0] if resume_episode else None
		if not play_item:
			next_up = EmbyApiClient.getNextUpEpisodeForSeries(series_id)
			play_item = next_up[0] if next_up else None
		if not play_item:
			episodes = EmbyApiClient.getEpisodesForSeries(series_id)
			if episodes:
				sorted_episodes = sorted(episodes, key=lambda ep: (ep.get("ParentIndexNumber", 0), ep.get("IndexNumber", 0)))
				play_item = sorted_episodes[0]
		if play_item:
			full_item = EmbyApiClient.getSingleItem(play_item.get("Id"))
			if full_item and full_item.get("Id"):
				self.startPlayback(full_item)

	def startPlayback(self, item):
		showLoadingScreen(self.session)
		startPos = int(item.get("UserData", {}).get("PlaybackPositionTicks", "0")) / 10_000_000
		playItem(item, self.session, self.playerExitCallback, startPos=startPos)

	def playerExitCallback(self, *result):
		self.last_widget_info_load_success = None
		self.onSelectedIndexChanged()

	def hideFunctionButtons(self):
		self.f_buttons_visible = False
		self.info_display_item = None
		if self.f_buttons_focused:
			self.f_buttons_focused = False
			self["f_buttons"].enableSelection(False)
			self.lists[self.selected_widget].enableSelection(True)
		self["f_buttons"].instance.hide()

	def showFunctionButtonsForItem(self, item):
		self.info_display_item = item
		self["f_buttons"].setSimpleButtons(item, self.playCurrentItem, self.openMoreInfo, keepSelection=self.f_buttons_focused)
		self.f_buttons_visible = True
		self["f_buttons"].instance.show()

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		if result == EXIT_RESULT_MOVIE:
			threads.deferToThread(self.reloadMovieWidgets)
		elif result in [EXIT_RESULT_SERIES, EXIT_RESULT_EPISODE]:
			threads.deferToThread(self.reloadSeriesWidgets)

	def reloadMovieWidgets(self):
		self.last_widget_info_load_success = None
		self.last_item_id = self[self.selected_widget].selectedItem.get("Id")
		if "list_watching" in self.availableWidgets:
			self.loadEmbyList(self["list_watching"], "Resume")
		if "list_recent_movies" in self.availableWidgets:
			self.loadEmbyList(self["list_recent_movies"], "LastMovies", self.movie_libs_ids)
		if not self[self.selected_widget].isLibrary:
			self.onSelectedIndexChanged()

	def reloadSeriesWidgets(self):
		self.last_widget_info_load_success = None
		self.last_item_id = self[self.selected_widget].selectedItem.get("Id")
		if "list_watching" in self.availableWidgets:
			self.loadEmbyList(self["list_watching"], "Resume")
		if "list_recent_tvshows" in self.availableWidgets:
			self.loadEmbyList(self["list_recent_tvshows"], "LastSeries", self.tvshow_libs_ids)
		if not self[self.selected_widget].isLibrary:
			self.onSelectedIndexChanged()

	BACKDROP_MAX_RETRIES = 3
	BACKDROP_RETRY_DELAY = 2

	def downloadCover(self, item_id, icon_img, orig_item_id, attempt=0):
		try:
			timed_out = []
			backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1280, image_type="Backdrop", alpha_channel=self.mask_alpha, on_timeout=lambda: timed_out.append(True))
			if orig_item_id != self.last_item_id:
				return
			if backdrop_pix:
				self["backdrop"].setPixmap(backdrop_pix)
				self.backdrop_pix = backdrop_pix
			elif timed_out and attempt < self.BACKDROP_MAX_RETRIES:
				sleep(self.BACKDROP_RETRY_DELAY)
				if orig_item_id != self.last_item_id:
					return
				self.downloadCover(item_id, icon_img, orig_item_id, attempt + 1)
			else:
				self["backdrop"].setPixmap(None)
				self.backdrop_pix = None
		except:
			pass

	def clearInfoPane(self):
		self.backdrop_pix = None
		self["backdrop"].setPixmap(None)
		self["title_logo"].setPixmap(None)
		self["title"].text = ""
		self["subtitle"].text = ""
		self["infoline"].updateInfo({})
		self["plot"].text = ""
		self.hideFunctionButtons()

	def loadSelectedItemDetails(self, item, widget):
		if not self.home_loaded:
			return

		if self.last_widget_info_load_success and self.last_widget_info_load_success == widget:
			return

		orig_item_id = item.get("Id")
		colType = item.get("CollectionType")
		isLib = colType is not None and colType != "BoxSet"

		if orig_item_id != self.last_item_id:
			return

		item_id = orig_item_id

		if isLib:
			self.last_widget_info_load_success = widget

			item = EmbyApiClient.getRandomItemFromLibrary(item_id, colType)
			item_id = item.get("Id")

		parent_b_item_id = item.get("ParentLogoItemId")
		if parent_b_item_id:
			item_id = parent_b_item_id

		logo_tag = item.get("ImageTags", {}).get("Logo", None)
		parent_logo_tag = item.get("ParentLogoImageTag", None)
		if parent_logo_tag:
			logo_tag = parent_logo_tag

		itemType = item.get("Type", None)

		if logo_tag:
			logo_widget_size = self["title_logo"].instance.size()
			max_w = logo_widget_size.width()
			max_h = logo_widget_size.height()
			self.logo_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=logo_tag, max_width=max_w, max_height=max_h, image_type="Logo", format="png")
			if self.logo_pix:
				self["title_logo"].setPixmap(self.logo_pix)
				self["title"].text = ""
			else:
				if itemType == "Episode":
					self["title"].text = " ".join(
						item.get("SeriesName", "").splitlines())
				else:
					self["title"].text = " ".join(
						item.get("Name", "").splitlines())
				self["title_logo"].setPixmap(None)
		else:
			if itemType == "Episode":
				self["title"].text = " ".join(
					item.get("SeriesName", "").splitlines())
			else:
				self["title"].text = " ".join(
					item.get("Name", "").splitlines())
			self["title_logo"].setPixmap(None)

		if itemType == "Episode":
			sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
			self["subtitle"].text = sub_title
			subtitlesize = self["subtitle"].getSize()
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig + subtitlesize[1])
			self["plot"].setText(" \n" * 2)
			plot_height_calc = self["plot"].getSize()[1]
			self["plot"].resize(self.plot_width_orig, plot_height_calc)
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(infolinepos.x(), self.plot_posy_orig + subtitlesize[1] - infolinesize[1] - 10)
		else:
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig)
			self["plot"].resize(self.plot_width_orig, self.plot_height_orig)
			self["subtitle"].text = ""
			infolinesize = self["infoline"].getSize()
			infolinepos = self["infoline"].instance.position()
			self["infoline"].move(
				infolinepos.x(), self.plot_posy_orig - infolinesize[1] - 10)

		self["infoline"].updateInfo(item)

		self["plot"].text = item.get("Overview", "")

		if isLib:
			self.showFunctionButtonsForItem(item)
		else:
			self.hideFunctionButtons()

		backdrop_image_tags = item.get("BackdropImageTags")
		parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
		if parent_backdrop_image_tags:
			backdrop_image_tags = parent_backdrop_image_tags

		if not backdrop_image_tags or len(backdrop_image_tags) == 0:
			self["backdrop"].setPixmap(None)
			self.backdrop_pix = None
			return

		icon_img = backdrop_image_tags[0]
		parent_b_item_id = item.get("ParentBackdropItemId")
		if parent_b_item_id:
			item_id = parent_b_item_id
		if orig_item_id != self.last_item_id:
			return
		threads.deferToThread(self.downloadCover, item_id, icon_img, orig_item_id)

	def loadUserBadges(self):
		avatar_pix = EmbyApiClient.getUserAvatar(size=60, border_width=4, border_color=EMBY_ACCENT_GREEN_RGB)
		is_premiere = EmbyApiClient.getIsPremiere()
		if self.loaded_connection != getActiveConnection():
			return

		if avatar_pix:
			self["avatar"].setPixmap(avatar_pix)
			self["avatar"].show()
		else:
			self["avatar"].hide()

		if is_premiere:
			premiere_pix = LoadPixmap(resolveFilename(SCOPE_GUISKIN, "icons/emby_premiere.png"))
			if not premiere_pix:
				premiere_pix = LoadPixmap(f"{plugin_dir}/emby_premiere.png")
			self["premiere_badge"].setPixmap(premiere_pix)
			self["premiere_badge"].show()
		else:
			self["premiere_badge"].hide()

	def loadHome(self, activeConnection):
		self.loaded_connection = activeConnection
		DIRECTORY_PARSER.listDirectory()
		EmbyApiClient.authorizeUser(activeConnection[1], activeConnection[2], activeConnection[3], activeConnection[4])
		self.loadUserBadges()
		libs = EmbyApiClient.getLibraries()
		libs_list = []
		i = 0
		if libs:
			skippedInLatest = EmbyApiClient.userData.get("Configuration", {}).get("LatestItemsExcludes", [])
			for lib in libs:
				colType = lib.get("CollectionType")
				if colType and colType == "movies" and lib.get("DisplayPreferencesId", "") not in skippedInLatest:
					self.movie_libs_ids.append(int(lib.get("Id")))

				if colType and colType == "tvshows" and lib.get("DisplayPreferencesId", "") not in skippedInLatest:
					self.tvshow_libs_ids.append(int(lib.get("Id")))

				if colType and colType == "music" and lib.get("DisplayPreferencesId", "") not in skippedInLatest:
					self.music_libs_ids.append(int(lib.get("Id")))

				libs_list.append((i, lib, lib.get('Name'), None, "0", True))
				i += 1
			self["list"].loadData(libs_list)

		if self.loadEmbyList(self["list_watching"], "Resume"):
			if "list_watching" not in self.availableWidgets:
				self.availableWidgets.append("list_watching")
		if self.movie_libs_ids:
			if self.loadEmbyList(self["list_recent_movies"], "LastMovies", self.movie_libs_ids):
				if "list_recent_movies" not in self.availableWidgets:
					self.availableWidgets.append("list_recent_movies")
		if self.tvshow_libs_ids:
			if self.loadEmbyList(self["list_recent_tvshows"], "LastSeries", self.tvshow_libs_ids):
				if "list_recent_tvshows" not in self.availableWidgets:
					self.availableWidgets.append("list_recent_tvshows")

		try:
			y = self.top_slot_y
			self.lists["list"].move(40, y).visible(True)
			y += self.lists["list"].getHeight() + 40
			if "list_watching" in self.availableWidgets:
				self.lists["list_watching"].move(40, y).visible(True).enableSelection(self.selected_widget == "list_watching")
				y += self.lists["list_watching"].getHeight() + 40
			if "list_recent_movies" in self.availableWidgets:
				self.lists["list_recent_movies"].move(40, y).visible(True).enableSelection(self.selected_widget == "list_recent_movies")
				y += self.lists["list_recent_movies"].getHeight() + 40
			if "list_recent_tvshows" in self.availableWidgets:
				self.lists["list_recent_tvshows"].move(40, y).visible(True).enableSelection(self.selected_widget == "list_recent_tvshows")
				y += self.lists["list_recent_tvshows"].getHeight() + 40
		except:
			pass

		self.home_loaded = True
		self.last_widget_info_load_success = None
		self.loadSelectedItemDetails(self[self.selected_widget].selectedItem, self[self.selected_widget])

	def __onClose(self):
		Path.unlink(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop.png", missing_ok=True)
		Path.unlink(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop_orig.jpg", missing_ok=True)
		Path.unlink(f"/tmp{EMBY_THUMB_CACHE_DIR}/poster.jpg", missing_ok=True)

	def loadEmbyList(self, widget, type, parent_ids=[]):
		items = []
		type_part = ""
		parent_part = ""
		sortBy = "DatePlayed"
		includeItems = "Movie"
		if type == "Resume":
			type_part = "/Resume"
			sortBy = "DatePlayed"
			includeItems = "Movie,Episode&MediaTypes=Video"
		elif type == "LastMovies":
			sortBy = "DateCreated"
			includeItems = "Movie&IsMovie=true&Recursive=true&Filters=IsNotFolder"
		elif type == "LastSeries":
			sortBy = "DateCreated"
			includeItems = "Series&IsFolder=true&Recursive=true"
		if not parent_ids:
			items.extend(EmbyApiClient.getItems(
				type_part, sortBy, includeItems, parent_part))
		else:
			for parent_id in parent_ids:
				parent_part = f"&ParentId={parent_id}"
				part_items = EmbyApiClient.getItems(type_part, sortBy, includeItems, parent_part)
				items.extend(part_items)
			if len(parent_ids) > 1:
				items = sorted(items, key=lambda x: x.get("DateCreated"), reverse=True)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			widget.loadData(list)
		return len(list) > 0

	def menu(self):
		self.session.open(EmbySetup)
