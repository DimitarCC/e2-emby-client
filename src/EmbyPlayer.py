# coding: utf-8

from requests import get, post, delete
from requests.exceptions import ReadTimeout
from uuid import uuid4
from time import sleep

from twisted.internet import threads

from enigma import eTimer, iPlayableService, eServiceReference
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.config import config
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.Progress import Progress
from Components.Sources.StaticText import StaticText
from Screens.AudioSelection import AudioSelection
from Screens.InfoBar import MoviePlayer
try:
	from Screens.InfoBarGenerics import SeekBar
except ImportError:
	from Screens.InfoBarGenerics import Seekbar as SeekBar
from Screens.MinuteInput import MinuteInput
from Tools.LoadPixmap import LoadPixmap
from Tools.SubtitleRenderer import SubtitleRenderer

from . import Globals
from .EmbyInfoLine import EmbyInfoLine
from .EmbyList import EmbyList
from .EmbyLoadingScreen import showLoadingScreen, hideLoadingScreen
from .EmbyPlayerInfobarInfo import EmbyPlayerInfobarInfo
from .EmbyRestClient import EmbyApiClient
from .EmbySkipIntroScreen import showSkipIntroScreen, hideSkipIntroScreen
from .EmbyUpNextScreen import showUpNextScreen, hideUpNextScreen, updateUpNextCountdown, moveUpNextSelectionLeft, moveUpNextSelectionRight, activateUpNextSelectedButton, UP_NEXT_COUNTDOWN_SECONDS
from .HelperFunctions import convert_ticks_to_time
from .Variables import SUBTITLE_TUPLE_SIZE, EMBY_THUMB_CACHE_DIR, DISTRO


class EmbyPlayer(MoviePlayer):
	MUSIC_COVER_SIZE = 640  # keep in sync with the "cover" widget's skin size below
	SEEKABLE_POLL_INTERVAL = 50  # ms - how often to poll isCurrentlySeekable() while waiting
	SEEKABLE_POLL_TIMEOUT = 10000  # ms - give up waiting for seekability after this long
	AUDIO_OFFSET_MIN_SETTLE_MS = 750  # ms - minimum time to let the reported position settle before trusting it

	skin = ["""<screen name="EmbyPlayer" position="fill" flags="wfNoBorder" backgroundColor="#ff000000">
					<widget name="audio_bg" position="0,0" size="e,e" zPosition="-2" backgroundColor="#00000000" alphaBlend="1" />
					<widget name="info_line" position="240,954" size="e-40-240,45" font="Regular; 35" fontAdditional="Bold;24" transparent="1" zPosition="5"  alphaBlend="1"/>
					<widget name="info_bkg" backgroundColor="#10111111" position="-2,540" zPosition="-1" size="e+4,315" widgetBorderWidth="1" widgetBorderColor="#444444"  alphaBlend="1"/>
		 			<widget name="poster" backgroundColor="#10111111" position="30,557" zPosition="2" size="187,280" cornerRadius="6" widgetBorderWidth="1" widgetBorderColor="#444444" scale="1"  alphaBlend="1"/>
					<widget name="cover" backgroundColor="#10111111" position="center,110" zPosition="1" size="640,640" cornerRadius="10" widgetBorderWidth="1" widgetBorderColor="#444444" scale="1"  alphaBlend="1"/>
					<widget name="music_title" position="center,770" size="1400,55" font="Bold;42" halign="center" valign="center" transparent="1" foregroundColor="white" noWrap="1" alphaBlend="1"/>
					<widget name="music_artist" position="center,830" size="1400,45" font="Regular;30" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" noWrap="1" alphaBlend="1"/>
					<widget name="list_chapters" position="35,560" size="e-70,310" iconWidth="340" iconHeight="188" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" transparent="1" alphaBlend="1"/>
		 			<widget name="info_panel_line" position="275,560" size="e-340,60" font="Bold;32" fontAdditional="Bold;28" transparent="1"  alphaBlend="1"/>
					<widget name="plot" position="275,630" size="e-340,230" alphatest="blend" font="Regular;30" transparent="1" alphaBlend="1"/>
					<eLabel backgroundColor="#10111111" position="60,900" zPosition="-1" size="e-120,115" cornerRadius="8" widgetBorderWidth="1" widgetBorderColor="#444444"  alphaBlend="1"/>
					<widget name="statusicon" position="120,935" zPosition="3" size="48,48" scale="1" pixmaps="icons/pvr/play.svg,icons/pvr/pause.svg,icons/pvr/stop.svg,icons/pvr/ff.svg,icons/pvr/rew.svg,icons/pvr/slow.svg" alphaBlend="1"/>
					<widget name="speed" foregroundColor="white" halign="left" position="200,935" size="48,48" font="Bold; 24" transparent="1" alphaBlend="1"/>
					<widget name="time_elapsed" position="210,905" size="100,51" font="Bold; 26" halign="right" valign="center" backgroundColor="#02111111" transparent="1" foregroundColor="#ffffff" alphaBlend="1"/>
					<widget name="time_remaining_total" position="e-270-10,905" size="200,51" font="Bold; 26" halign="right" valign="center" backgroundColor="#02111111" transparent="1" foregroundColor="#ffffff" alphaBlend="1"/>
					<widget source="progress" render="Progress" backgroundColor="#02333333" foregroundColor="#32772b" position="340,925" zPosition="2" size="e-260-340,12" transparent="1" cornerRadius="6" alphaBlend="1"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session, item=None, startPos=None, slist=None, lastservice=None, is_trailer=False, trailer_url=None, queue=None, queue_index=0):
		Globals.IsPlayingFile = True
		item = item or {}
		ref, play_session_id, defaultAudioIndex, defaultSubtitleIndex = self.buildServiceRef(item, is_trailer, trailer_url)
		MoviePlayer.__init__(self, session, service=ref, slist=slist, lastservice=lastservice)
		self.session = session
		# Queue state is session-scoped (persists/increments across tracks as the
		# queue advances) rather than per-item state, so it lives here rather than
		# in setPlayingItem() - see playNextQueuedTrack().
		self.queue = queue
		self.queue_index = queue_index
		AudioSelection.fillSubtitleExt = self.subtitleListIject
		if self.onAudioSubTrackChanged not in AudioSelection.hooks:
			AudioSelection.hooks.append(self.onAudioSubTrackChanged)
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.onHide.append(self.__onHide)
		self.onLayoutFinish.append(self.__onLayoutFinished)
		self.selectedSubtitleTrack = (0, 0, 0, 0, "und")
		self["audio_bg"] = Label("")
		self["audio_bg"].hide()
		self["poster"] = Pixmap()
		self["poster"].hide()
		self["cover"] = Pixmap()
		self["cover"].hide()
		self["music_title"] = Label("")
		self["music_title"].hide()
		self["music_artist"] = Label("")
		self["music_artist"].hide()
		self["info_panel_line"] = EmbyInfoLine(self)
		self["info_panel_line"].hide()
		self["plot"] = Label()
		self["plot"].hide()
		self["info_line"] = EmbyPlayerInfobarInfo(self)
		self["list_chapters"] = EmbyList(type="chapters")
		self["list_chapters"].hide()
		self["progress"] = Progress()
		self["progress_summary"] = Progress()
		self["progress"].value = 0
		self["progress_summary"].value = 0
		self["info_bkg"] = Label("")
		self["info_bkg"].hide()
		self["time_info"] = Label("")
		self["time_elapsed"] = Label("")
		self["time_duration"] = Label("")
		self["time_remaining"] = Label("")
		self["time_remaining_total"] = Label("")
		self["time_info_summary"] = StaticText("")
		self["time_elapsed_summary"] = StaticText("")
		self["time_duration_summary"] = StaticText("")
		self["time_remaining_summary"] = StaticText("")
		self.init_timer = eTimer()
		self.init_timer.callback.append(self.__onPlayerInit)
		# Poll for a seekable service right away instead of waiting for
		# evStart - on servicehisilicon, evStart fires only after the
		# decoder is already showing picture from position 0, so waiting
		# for it makes the resume seek visibly land ~1s late.
		self.init_timer.start(50)
		self.progress_timer = eTimer()
		self.progress_timer.callback.append(self.onProgressTimer)
		self.emby_progress_timer = eTimer()
		self.emby_progress_timer.callback.append(self.updateEmbyProgress)
		self.seek_timer = eTimer()
		self.seek_timer.callback.append(self.onSeekRequest)
		self.up_next_countdown_timer = eTimer()
		self.up_next_countdown_timer.callback.append(self.onUpNextCountdownTick)
		self.audio_track_settle_timer = eTimer()
		self.audio_track_settle_timer.callback.append(self.onAudioSubTrackChanged)
		self.init_audio_track_settle_timer = eTimer()
		self.init_audio_track_settle_timer.callback.append(self.__onInitAudioTrackSettle)
		self.init_audio_track_retries = 0
		self.init_audio_track_index = -1
		self.seekable_wait_timer = eTimer()
		self.seekable_wait_timer.callback.append(self.__onSeekableWaitTick)
		self.seekable_wait_callback = None
		self.seekable_wait_elapsed = 0
		self.audio_offset_recheck_timer = eTimer()
		self.audio_offset_recheck_timer.callback.append(self.__onAudioOffsetRecheckTick)
		self.audio_offset_recheck_target = None
		self.audio_offset_recheck_last_pos = None
		self.audio_offset_recheck_stable_ms = 0
		self.audio_offset_recheck_elapsed = 0
		self.setPlayingItem(item, startPos, is_trailer, play_session_id, defaultAudioIndex, defaultSubtitleIndex)
		self.onProgressTimer()
		self["NumberSeekActions"] = NumberActionMap(["NumberActions"],
		{
			"1": self.numberSeek,
			"3": self.numberSeek,
			"4": self.numberSeek,
			"6": self.numberSeek,
			"7": self.numberSeek,
			"9": self.numberSeek,
		}, -10)
		self["InfobarMovieActions"] = ActionMap(["E2EmbyActions", "InfobarEPGActions", "ButtonSetupActions", "InfobarMovieListActions"],
		{
			"up": self.showChapters,
			"down": self.showNextPlaylist,
			"movieList": self.showChapters,
			"InfoPressed": self.showInfo,
			"EPGPressed": self.showInfo,
			"epg": self.showInfo,
			"ok": self.processItem,
		}, -15)
		self.subtitle_renderer = SubtitleRenderer(self)
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: self.__evServiceStartInit,
			iPlayableService.evUpdatedInfo: self.__updatedInfoEmby})

	def buildServiceRef(self, item, is_trailer, trailer_url):
		item_id = int(item.get("Id", "0"))
		item_name = item.get("Name", "Stream")
		media_sources = item.get("MediaSources")
		ref = None
		play_session_id = ""
		defaultAudioIndex = -1
		defaultSubtitleIndex = -1
		if media_sources and not is_trailer:
			media_source = media_sources[0]
			defaultAudioIndex = media_source.get("DefaultAudioStreamIndex", -1)
			defaultSubtitleIndex = media_source.get("DefaultSubtitleStreamIndex", -1)
			container = media_source.get("Container")
			media_source_id = media_source.get("Id")
			play_session_id = str(uuid4())
			if item.get("Type") == "Audio":
				directStreamUrl = f"/audio/{item_id}/stream.{container}?static=true&DeviceId={EmbyApiClient.device_id}&MediaSourceId={media_source_id}&PlaySessionId={play_session_id}&api_key={EmbyApiClient.access_token}"
			else:
				directStreamUrl = f"/videos/{item_id}/original.{container}?DeviceId={EmbyApiClient.device_id}&MediaSourceId={media_source_id}&PlaySessionId={play_session_id}&api_key={EmbyApiClient.access_token}"
			url = f"{EmbyApiClient.server_root}{directStreamUrl}"
			ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % (config.plugins.e2embyclient.play_system.value, item_id, url.replace(":", "%3a"), item_name))
		if is_trailer and trailer_url:
			ref = eServiceReference("%s:0:1:%x:1010:1:CCCC0000:0:0:0:%s:%s" % (config.plugins.e2embyclient.play_system.value, item_id, trailer_url.replace(":", "%3a"), f"Trailer - {item_name}"))
		if ref is None:
			print(f"[EmbyPlayer] ERROR ref is None for item '{item}'")
			print(f" is_trailer -> {is_trailer}")
			print(f" media_sources -> {media_sources}")
			print(f" trailer_url -> {trailer_url}")
		return ref, play_session_id, defaultAudioIndex, defaultSubtitleIndex

	def setPlayingItem(self, item, startPos, is_trailer, play_session_id, defaultAudioIndex, defaultSubtitleIndex):
		self.audio_track_settle_timer.stop()
		self.audio_track_settle_checked = False
		self.init_audio_track_settle_timer.stop()
		self.init_audio_track_retries = 0
		self.init_audio_track_index = -1
		self.__cancelSeekableWait()
		self.__cancelAudioOffsetRecheck()
		self.is_trailer = is_trailer
		self.init_seek_to = startPos
		self.init_seek_is_nudge = False
		self.post_track_switch_seek_target = None
		self.audio_pos_offset = 0
		self.curAudioIndex = -1
		self.CurIndexEmbeddedSubs = -1
		self.curSubsIndex = -1
		self.firstSubIndex = -1
		self.supressChapterSelect = False
		self.item = item or {}
		self.chapters = []
		self.introStartPos = None
		self.introEndPos = None
		self.skipIntroShown = False
		self.skipIntroDismissed = False
		self.upNextEligible = self.item.get("Type") == "Episode" and not is_trailer
		self.upNextItem = None
		self.upNextShown = False
		self.upNextDismissed = False
		self.upNextSecondsLeft = UP_NEXT_COUNTDOWN_SECONDS
		self.play_session_id = play_session_id
		self.skip_progress_update = False
		self.current_seek_step = 0
		self.current_pos = -1
		self.lastPos = -1
		self.selected_widget = None
		self.is_audio = self.item.get("Type") == "Audio" and not is_trailer
		if is_trailer:
			self["info_line"].updateInfo(self.item, -1, -1, True)
		else:
			self["info_line"].updateInfo(self.item, defaultAudioIndex, defaultSubtitleIndex)
		self["info_panel_line"].updateInfo(self.item)
		self.loadChapters()
		if self.upNextEligible:
			threads.deferToThread(self.fetchUpNextItem)
		self.info_shown = False
		self.updateMusicDisplay()

	def updateMusicDisplay(self):
		if self.instance:
			self.instance.setWidgetAlphaBlend(self.is_audio)
		if not self.is_audio:
			self["audio_bg"].hide()
			self["cover"].hide()
			self["music_title"].hide()
			self["music_artist"].hide()
			return
		# There's no video for an audio-only stream, so the base MoviePlayer's
		# auto-hide timer would otherwise hide this whole screen after a few
		# seconds of inactivity, exposing Enigma2's own radio-mode background
		# behind it - keep the OSD up and an opaque layer in front of that at
		# all times while a track is playing (see startHideTimer() override
		# and the periodic backstop in onProgressTimer()).
		self.hideTimer.stop()
		self["audio_bg"].show()
		artist = self.item.get("AlbumArtist") or ", ".join(self.item.get("Artists") or [])
		album = self.item.get("Album", "")
		self["music_title"].setText(" ".join(self.item.get("Name", "").splitlines()))
		self["music_artist"].setText(" • ".join(p for p in (artist, album) if p))
		self["music_title"].show()
		self["music_artist"].show()
		if self["cover"].instance:
			# .instance isn't bound yet the first time this runs - it's reached
			# from setPlayingItem() during __init__, before the screen's skin/
			# widgets are applied, and unlike .hide()/.show()/Label.setText(),
			# Pixmap.setPixmap() isn't defensive against a None instance.
			self["cover"].setPixmap(None)
		self["cover"].hide()
		threads.deferToThread(self.loadMusicCover, self.item)

	def loadMusicCover(self, item):
		item_id = item.get("Id")
		icon_img = (item.get("ImageTags") or {}).get("Primary")
		if not icon_img:
			album_id = item.get("AlbumId")
			album_tag = item.get("AlbumPrimaryImageTag")
			if album_id and album_tag:
				item_id = album_id
				icon_img = album_tag
		if not icon_img:
			return
		# self["cover"].instance isn't bound yet the first time this runs (this
		# is reached from setPlayingItem() during __init__, before the screen's
		# skin/widgets are applied), so use the skin's cover size directly
		# instead of instance.size().
		pix_path = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=self.MUSIC_COVER_SIZE, height=self.MUSIC_COVER_SIZE, image_type="Primary")
		if not self.is_audio or item.get("Id") != self.item.get("Id"):
			return
		# getItemImage() returns a cached file path for "Primary" (only "Logo"
		# or an alpha_channel request get a pre-loaded pixmap back) - callers
		# are expected to LoadPixmap() it themselves, same as EmbyList/
		# EmbyGridList/EmbyMusicRowList do in their buildEntry().
		pix = pix_path and LoadPixmap(pix_path)
		if pix and self["cover"].instance:
			self["cover"].setPixmap(pix)
			self["cover"].show()

	def startHideTimer(self):
		# self.is_audio isn't set yet if the base MoviePlayer.__init__() (which
		# runs before our setPlayingItem() call) triggers this itself.
		if getattr(self, "is_audio", False):
			self.hideTimer.stop()
			return
		MoviePlayer.startHideTimer(self)

	def __onLayoutFinished(self):
		# self["cover"]/self.instance aren't bound until now (see the
		# .instance guards in updateMusicDisplay()/loadMusicCover(), reached
		# earlier from setPlayingItem() during __init__) - re-run it once the
		# skin is actually applied so the alpha-blend widget flag from below
		# gets set for a track that started playing before layout finished.
		# hide() before that point leaves the widgets on screen, and audio_bg
		# covers the whole video plane.
		self.updateMusicDisplay()

	def __onHide(self):
		self["list_chapters"].hide()
		self["info_bkg"].hide()
		self["poster"].hide()
		self["info_panel_line"].hide()
		self["plot"].hide()
		self.hideSkipIntroButton()
		self.hideUpNextOverlay(dismiss=True)
		self.selected_widget = None
		self.info_shown = False
		self.supressChapterSelect = False

	def loadChapters(self):
		if self.is_trailer:
			return
		media_sources = self.item.get("MediaSources", [])
		if not media_sources:
			return
		# MediaSources[0] is always the version being played (playItem() moves
		# the user-selected version to the front), so chapters must come from
		# it too rather than from whichever source happens to have Type=="Default".
		playing_media_source = media_sources[0]
		all_chapters = playing_media_source.get("Chapters", [])
		# Ordinary chapters may carry MarkerType too (e.g. "Chapter"), so only
		# the intro markers themselves must be excluded from the chapter list -
		# filtering on plain truthiness would drop every chapter whenever the
		# server tags regular chapters with a non-empty MarkerType.
		self.chapters = [ch for ch in all_chapters if ch.get("MarkerType") not in ("IntroStart", "IntroEnd")]
		intro_start = next((ch for ch in all_chapters if ch.get("MarkerType") == "IntroStart"), None)
		intro_end = next((ch for ch in all_chapters if ch.get("MarkerType") == "IntroEnd"), None)
		if intro_start:
			self.introStartPos = int(intro_start.get("StartPositionTicks", "0")) / 10_000_000
		if intro_end:
			self.introEndPos = int(intro_end.get("StartPositionTicks", "0")) / 10_000_000

	def fetchUpNextItem(self):
		series_id = self.item.get("SeriesId")
		if not series_id:
			return
		episodes = EmbyApiClient.getEpisodesForSeries(series_id)
		if not episodes:
			return
		sorted_episodes = sorted(episodes, key=lambda ep: (ep.get("ParentIndexNumber", 0), ep.get("IndexNumber", 0)))
		current_id = self.item.get("Id")
		current_index = next((i for i, ep in enumerate(sorted_episodes) if ep.get("Id") == current_id), -1)
		if current_index == -1 or current_index + 1 >= len(sorted_episodes):
			return
		next_item_id = sorted_episodes[current_index + 1].get("Id")
		next_item = EmbyApiClient.getSingleItem(next_item_id)
		if next_item and next_item.get("Id"):
			self.upNextItem = next_item

	def showUpNextOverlay(self):
		self.upNextShown = True
		self.upNextSecondsLeft = UP_NEXT_COUNTDOWN_SECONDS
		showUpNextScreen(self.session, self.upNextItem, self.playUpNextItem, self.hideUpNextOverlay)
		self.up_next_countdown_timer.start(1000)

	def hideUpNextOverlay(self, dismiss=True):
		if self.upNextShown:
			self.up_next_countdown_timer.stop()
			hideUpNextScreen()
			self.upNextShown = False
		self.upNextDismissed = dismiss

	def onUpNextCountdownTick(self):
		self.upNextSecondsLeft -= 1
		if self.upNextSecondsLeft <= 0:
			self.up_next_countdown_timer.stop()
			self.playUpNextItem()
			return
		updateUpNextCountdown(self.upNextSecondsLeft)

	def playUpNextItem(self):
		next_item = self.upNextItem
		if not next_item:
			return
		ref, play_session_id, defaultAudioIndex, defaultSubtitleIndex = self.buildServiceRef(next_item, False, None)
		if ref is None:
			self.hideUpNextOverlay(dismiss=True)
			return
		self.__evServiceEnd()
		self.__onHide()
		showLoadingScreen(self.session)
		self.setPlayingItem(next_item, 0, False, play_session_id, defaultAudioIndex, defaultSubtitleIndex)
		self.session.nav.playService(ref)

	def hasNextQueuedTrack(self):
		return bool(self.queue) and self.queue_index + 1 < len(self.queue)

	def playNextQueuedTrack(self):
		# Mirrors playUpNextItem()'s low-level mechanics (advance to a new item
		# without closing/reopening the player screen), but with no overlay or
		# countdown - music auto-advance should be immediate and silent.
		if not self.hasNextQueuedTrack():
			return
		self.queue_index += 1
		next_item = self.queue[self.queue_index]
		ref, play_session_id, defaultAudioIndex, defaultSubtitleIndex = self.buildServiceRef(next_item, False, None)
		if ref is None:
			return
		self.__evServiceEnd()
		self.__onHide()
		showLoadingScreen(self.session)
		self.setPlayingItem(next_item, 0, False, play_session_id, defaultAudioIndex, defaultSubtitleIndex)
		self.session.nav.playService(ref)

	def updateUpNextScreen(self, pos):
		if not config.plugins.e2embyclient.show_up_next_screen.value:
			return
		if self.skipIntroShown or not self.upNextEligible or not self.upNextItem:
			return
		length = self.getLength()
		if not length:
			return
		remaining = length - pos
		if remaining <= UP_NEXT_COUNTDOWN_SECONDS:
			if not self.upNextShown and not self.upNextDismissed:
				self.showUpNextOverlay()
		else:
			self.upNextDismissed = False

	def __maybeArmAudioOffsetRecheck(self, target_seconds):
		# servicemp3/HiPlayer can re-trigger a fresh (and possibly different)
		# bogus reported-position offset on ANY seek, not just ones landing
		# near the start of the stream, and the offset then stays constant
		# for playback until the next seek - so re-measure it after every
		# seek whose true target we know, rather than only near start.
		if self.is_audio and config.plugins.e2embyclient.play_system.value == "4097" and target_seconds >= 0:
			self.__armAudioOffsetRecheck(target_seconds)

	def doSeek(self, pts):
		MoviePlayer.doSeek(self, pts)
		self.__maybeArmAudioOffsetRecheck(pts / 90000)

	def doSeekRelative(self, pts):
		before = self.getPosition() or 0
		MoviePlayer.doSeekRelative(self, pts)
		self.__maybeArmAudioOffsetRecheck(before + pts / 90000)

	def __openSeekbarOrMinuteInput(self, fwd, use_seekbar):
		# The on-screen Seekbar calls iSeekableService.seekTo() directly once
		# closed, bypassing doSeek()/doSeekRelative() entirely - reimplement
		# the base class's dispatch (InfoBarGenerics.seekFwdSeekbar/
		# seekBackSeekbar/seekFwdManual/seekBackManual/seekFwdVod all funnel
		# into this same choice) with our own callback so a Seekbar-driven
		# seek can still be caught once it actually lands.
		if use_seekbar:
			self.session.openWithCallback(self.__onSeekbarClosed, SeekBar, fwd)
		elif fwd:
			self.session.openWithCallback(self.fwdSeekTo, MinuteInput)
		else:
			self.session.openWithCallback(self.rwdSeekTo, MinuteInput)

	def __onSeekbarClosed(self, *result):
		# The Seekbar computes its target as length*percent internally and
		# never exposes it, so there's no true target to compare against
		# here (unlike doSeek()/doSeekRelative() below, where we know it
		# exactly) - use the raw reading right at close time as a best-effort
		# stand-in target, then let __armAudioOffsetRecheck's settle-poll
		# detect whether the backend's reported position drifts away from it.
		seekable = self.__getSeekableService()
		pos = seekable and seekable.getPlayPosition()
		if pos is not None and not pos[0]:
			self.__maybeArmAudioOffsetRecheck(pos[1] / 90000)

	def seekBack(self):
		if self.upNextShown:
			moveUpNextSelectionLeft()
			return
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekBack(self)
		self.showAfterSeek()

	def left(self):
		if self.upNextShown:
			moveUpNextSelectionLeft()
			return
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveLeft)

	def seekFwd(self):
		if self.upNextShown:
			moveUpNextSelectionRight()
			return
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekFwd(self)
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekFwdManual(self, fwd=True):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		self.__openSeekbarOrMinuteInput(fwd, config.seek.baractivation.value == "leftright")
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekBackManual(self, fwd=False):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		self.__openSeekbarOrMinuteInput(fwd, config.seek.baractivation.value == "leftright")
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekBackSeekbar(self, fwd=False):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		self.__openSeekbarOrMinuteInput(fwd, config.seek.baractivation.value != "leftright")

	def seekFwdSeekbar(self, fwd=True):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		self.__openSeekbarOrMinuteInput(fwd, config.seek.baractivation.value != "leftright")

	def seekFwdVod(self, fwd=True):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		if self.getSeek() is None:
			return
		self.__openSeekbarOrMinuteInput(fwd, config.seek.baractivation.value == "leftright")

	def right(self):
		if self.upNextShown:
			moveUpNextSelectionRight()
			return
		if self.skipIntroShown:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveRight)

	def processItem(self):
		if self.upNextShown:
			activateUpNextSelectedButton()
			return
		if self.skipIntroShown:
			self.skipIntro()
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			chapter = self["list_chapters"].selectedItem
			startPos = int(chapter.get("StartPositionTicks", "0")) / 10_000_000
			self.doSeek(int(startPos) * 90000)
			self.showAfterSeek()
		elif self.is_audio:
			# OK is a no-op during music playback: the OSD is kept
			# permanently visible for audio (see updateMusicDisplay()), so
			# toggleShow() would hide it with nothing left showing, which
			# reads as the player having closed.
			pass
		else:
			if DISTRO != "openatv":
				self.toggleShow()
			MoviePlayer.okButton(self)

	def find_current_chapter_index(self):
		pts = self.getPosition()
		for i in range(len(self.chapters) - 1):
			startPos = int(self.chapters[i].get("StartPositionTicks", "0")) / 10_000_000
			startPosNext = int(self.chapters[i + 1].get("StartPositionTicks", "0")) / 10_000_000
			if startPos <= pts < startPosNext:
				return i
		return len(self.chapters) - 1  # Last chapter

	def showChapters(self):
		if self.upNextShown or self.skipIntroShown:
			return
		if self.chapters and not self.is_trailer:
			list = []
			i = 0
			for ch in self.chapters:
				pos_ticks = int(ch.get("StartPositionTicks"))
				ch["Id"] = f"{self.item.get('Id')}_{ch.get("ChapterIndex")}"
				list.append((i, ch, f"{ch.get('Name')}\n{convert_ticks_to_time(pos_ticks, True)}", None, "0", True))
				i += 1
			self["list_chapters"].loadData(list)
			self["list_chapters"].show()
			self["info_bkg"].show()
			self.selected_widget = "list_chapters"
			self["list_chapters"].instance.moveSelectionTo(self.find_current_chapter_index())
			self.showAfterSeek()
			self.hideTimer.stop()
		else:
			self["list_chapters"].hide()

	def showInfo(self):
		if self.upNextShown or self.skipIntroShown:
			return
		if self.is_trailer:
			return
		if self.is_audio:
			return
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.__onHide()

		if not self.info_shown:
			self["poster"].show()
			poster_path = f"/tmp{EMBY_THUMB_CACHE_DIR}/poster.jpg"
			self["poster"].setPixmap(LoadPixmap(poster_path))
			self["info_panel_line"].show()
			self["plot"].text = self.item.get("Overview", "")
			self["plot"].show()
			self["info_bkg"].show()
			self.showAfterSeek()
			self.hideTimer.stop()
			self.info_shown = True
		else:
			self["poster"].hide()
			self["info_panel_line"].hide()
			self["plot"].hide()
			self["info_bkg"].hide()
			self.info_shown = False
			self.showAfterSeek()

	def showNextPlaylist(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self["list_chapters"].hide()
			self["info_bkg"].hide()
			self.selected_widget = None
			self.supressChapterSelect = False
			self.showAfterSeek()

	def getLength(self):
		seek = self.getSeek()
		if seek is None:
			return None
		length = seek.getLength()
		if length[0]:
			return 0
		return length[1] / 90000

	def getPosition(self):
		seek = self.getSeek()
		if seek is None:
			return None
		pos = seek.getPlayPosition()
		if pos[0]:
			return 0
		raw = pos[1] / 90000
		if self.is_audio and self.audio_pos_offset:
			# servicemp3/HiPlayer keeps reporting true_position + audio_pos_offset
			# for the entire remainder of playback since the last seek, once
			# the bug triggers - audible playback itself is unaffected and
			# stays perfectly continuous, only the reported position is off,
			# so the same constant correction applies until the next seek
			# re-measures it (see __maybeArmAudioOffsetRecheck).
			return max(0, raw - self.audio_pos_offset)
		return raw

	def numberSeek(self, key):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
		if self.skipIntroShown:
			return

		if self.getSeek() is None:  # not currently seekable, so skip this key press
			return
		self.seek_timer.stop()
		p = self.getPosition()
		self.current_seek_step += {1: - config.seek.selfdefined_13.value, 3: config.seek.selfdefined_13.value, 4: - config.seek.selfdefined_46.value, 6: config.seek.selfdefined_46.value, 7: - config.seek.selfdefined_79.value, 9: config.seek.selfdefined_79.value}[key]
		self.progress_timer.stop()
		self.seek_timer.start(1000, True)
		p += self.current_seek_step
		self.skip_progress_update = True
		self.current_pos = p
		self.setProgress(p)
		self.showAfterSeek()  # show infobar

	def onSeekRequest(self):
		self.seek_timer.stop()
		self.doSeekRelative(self.current_seek_step * 90000)
		self.updateEmbyProgress()
		self.current_seek_step = 0
		self.current_pos = -1
		self.skip_progress_update = False
		self.progress_timer.start(1000)

	def setProgress(self, pos):
		if pos and pos > 0:
			self.lastPos = pos
		else:
			self.lastPos = self.init_seek_to

		lenght = self.getLength()
		if not lenght or pos is None:
			self["progress"].value = 0
			self["progress_summary"].value = 0
			text = "-00:00:00         00:00:00         +00:00:00"
			self["time_info"].setText(text)
			self["time_info_summary"].setText(text)
			text_elapsed = "-00:00:00"
			self["time_elapsed"].setText(text_elapsed)
			self["time_elapsed_summary"].setText(text_elapsed)
			text_duration = "00:00:00"
			self["time_duration"].setText(text_duration)
			self["time_duration_summary"].setText(text_duration)
			text_remaining = "+00:00:00"
			self["time_remaining"].setText(text_remaining)
			self["time_remaining_total"].setText(text_remaining + " / " + text_duration)
			self["time_remaining_summary"].setText(text_remaining)
			return

		r = self.getLength() - pos  # Remaining
		progress_val = i if (i := int((pos / lenght) * 100)) and i >= 0 else 0
		self["progress"].value = progress_val
		self["progress_summary"].value = progress_val
		text = "-%d:%02d:%02d         %d:%02d:%02d         +%d:%02d:%02d" % (pos / 3600, pos % 3600 / 60, pos % 60, lenght / 3600, lenght % 3600 / 60, lenght % 60, r / 3600, r % 3600 / 60, r % 60)
		self["time_info"].setText(text)
		self["time_info_summary"].setText(text)
		text_elapsed = "-%d:%02d:%02d" % (pos / 3600, pos % 3600 / 60, pos % 60)
		self["time_elapsed"].setText(text_elapsed)
		self["time_elapsed_summary"].setText(text_elapsed)
		text_duration = "%d:%02d:%02d" % (lenght / 3600, lenght % 3600 / 60, lenght % 60)
		self["time_duration"].setText(text_duration)
		self["time_duration_summary"].setText(text_duration)
		text_remaining = "+%d:%02d:%02d" % (r / 3600, r % 3600 / 60, r % 60)
		self["time_remaining"].setText(text_remaining)
		self["time_remaining_total"].setText(text_remaining + " / " + text_duration)
		self["time_remaining_summary"].setText(text_remaining)

	def onProgressTimer(self):
		if self.is_audio:
			# Backstop for startHideTimer() below - runs every second, so the
			# hide timer never accumulates enough idle time to fire even if
			# some base-class path re-arms it directly instead.
			self.hideTimer.stop()
		curr_pos = self.getPosition()
		if not curr_pos:
			curr_pos = 0
		if not self.skip_progress_update or self.is_trailer:
			self.setProgress(curr_pos if self.current_pos == -1 else self.current_pos)
		if self.selected_widget == "list_chapters" and not self.supressChapterSelect:
			cur_ch_index = self.find_current_chapter_index()
			if cur_ch_index != self["list_chapters"].getCurrentIndex():
				self["list_chapters"].instance.moveSelectionTo(cur_ch_index)
		self.updateSkipIntroButton(curr_pos)
		self.updateUpNextScreen(curr_pos)

	def updateSkipIntroButton(self, pos):
		if not config.plugins.e2embyclient.show_skip_intro_button.value:
			return
		if self.introStartPos is None or self.introEndPos is None or self.is_trailer:
			return
		if self.introStartPos <= pos < self.introEndPos:
			if not self.skipIntroShown and not self.skipIntroDismissed:
				showSkipIntroScreen(self.session)
				self.skipIntroShown = True
		else:
			self.hideSkipIntroButton()
			if pos < self.introStartPos:
				self.skipIntroDismissed = False

	def hideSkipIntroButton(self):
		if self.skipIntroShown:
			hideSkipIntroScreen()
			self.skipIntroShown = False

	def skipIntro(self):
		self.doSeek(int(self.introEndPos) * 90000)
		self.skipIntroDismissed = True
		self.hideSkipIntroButton()

	def updateEmbyProgress(self):
		if self.is_trailer:
			return
		threads.deferToThread(self.updateEmbyProgressInternal, "TimeUpdate", self.current_pos)

	def isPosWithinBounds(self, pos):
		if pos is None or pos < 0:
			return False
		length = self.getLength()
		if length and pos > length:
			return False
		return True

	def updateEmbyProgressInternal(self, event, pos=-1):
		if self.is_trailer:
			return
		if pos == -1:
			pos = self.getPosition()
		if not self.isPosWithinBounds(pos):
			for _ in range(3):
				sleep(1)
				pos = self.getPosition()
				if self.isPosWithinBounds(pos):
					break
			else:
				return
		ticks = int(pos) * 10_000_000
		item_id = self.item.get("Id")
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return
		media_source = media_sources[0]
		media_source_id = media_source.get("Id")
		EmbyApiClient.updateProgress(self.play_session_id, item_id, media_source_id, event, self.curAudioIndex, self.curSubsIndex, ticks)

	def loadAndParseSubs(self, stream_url):
		try:
			response = get(stream_url, timeout=5)
			if response.status_code != 404:
				intermediate_text = response.content.decode("utf-8", errors='replace')
				try:
					intermediate_bytes = intermediate_text.encode('latin1')
					subs_file = intermediate_bytes.decode(config.plugins.e2embyclient.encodding_nonutf_subs.value)
				except:
					subs_file = intermediate_text
				self.subtitle_renderer.loadSubtitles(subs_file, "SRT")
				return True
		except:
			pass
		return False

	def runSubtitles(self, subtitle, sindex=-1):
		if not subtitle and sindex > -1:
			return

		if not subtitle:
			self.subtitle_renderer.stopSubtitles()
			self.selected_subtitle = (0, 0, 0, 0, "")
			self.curSubsIndex = -1
			self.updateEmbyProgressInternal("SubtitleTrackChange")
			if self.is_trailer:
				self["info_line"].updateInfo(self.item, -1, -1, True)
			else:
				self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)
			return

		self.enableSubtitle(None)
		subs_uri = subtitle[SUBTITLE_TUPLE_SIZE + 1]
		threads.deferToThread(self.downloadAndRunSubs, subs_uri, subtitle)

	def downloadAndRunSubs(self, subs_uri, subtitle):
		result = self.loadAndParseSubs(subs_uri)
		if result:
			self.subtitle_renderer.startSubtitle()
			self.selected_subtitle = subtitle
			self.curSubsIndex = subtitle[3]
			self.updateEmbyProgressInternal("SubtitleTrackChange")
			if self.is_trailer:
				self["info_line"].updateInfo(self.item, -1, -1, True)
			else:
				self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)
		else:
			pass  # TODO: add message, log, etc...

	def subtitleListIject(self, subtitlesList):
		item_id = int(self.item.get("Id", "0"))
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return
		media_source = media_sources[0]
		media_streams = media_source.get("MediaStreams")
		if len(subtitlesList) > 0:
			i = subtitlesList[-1][1] + 1
		else:
			i = 1
		subtitletracks = [sub for sub in media_streams if sub.get("Type") == "Subtitle" and sub.get("IsExternal")]
		for stream in subtitletracks:
			index = int(stream.get("Index"))
			subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{index}/stream.srt?api_key={EmbyApiClient.access_token}"
			if SUBTITLE_TUPLE_SIZE == 5:
				subtitlesList.append((2, i, 4, index, stream.get("Language"), self.runSubtitles, subs_uri))
			else:
				subtitlesList.append((2, i, 4, index, stream.get("Language"), "", self.runSubtitles, subs_uri))
			i += 1

	def getEmbyTrackLists(self):
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return [], []
		media_source = media_sources[0]
		media_streams = media_source.get("MediaStreams")
		audiotracks = [au for au in media_streams if au.get("Type") == "Audio"]
		subtitletracks = [sub for sub in media_streams if sub.get("Type") == "Subtitle"]
		return audiotracks, subtitletracks

	def getSelectedAudioSubStreamFromEmby(self):
		aIndex = 0
		curAudioIndex = 0
		sindex = -1
		subtitle = None
		item_id = int(self.item.get("Id", "0"))
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return 0, None
		media_source = media_sources[0]
		audiotracks, subtitletracks = self.getEmbyTrackLists()
		defaultAudioIndex = media_source.get("DefaultAudioStreamIndex", -1)
		defaultSubtitleIndex = media_source.get("DefaultSubtitleStreamIndex", -1)
		aIndex = next((i for i, track in enumerate(audiotracks) if track.get("Index") == defaultAudioIndex), 0)
		if audiotracks:
			curAudioIndex = audiotracks[aIndex].get("Index")

		if defaultSubtitleIndex > -1 and subtitletracks:
			sindex = next((i for i, track in enumerate(subtitletracks) if track.get("Index") == defaultSubtitleIndex), -1)
			if sindex > -1:
				subtitle_obj = subtitletracks[sindex]
				isExternal = subtitle_obj.get("IsExternal")
				sub_index_emby = subtitle_obj.get("Index")
				if isExternal:
					subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{sub_index_emby}/stream.srt?api_key={EmbyApiClient.access_token}"
					if SUBTITLE_TUPLE_SIZE == 5:
						subtitle = (2, sindex + 1, 4, sub_index_emby, subtitle_obj.get("Language"), self.runSubtitles, subs_uri)
					else:
						subtitle = (2, sindex + 1, 4, sub_index_emby, subtitle_obj.get("Language"), "", self.runSubtitles, subs_uri)
					sindex = -1

		return aIndex, curAudioIndex, subtitle, sindex

	def onAudioSubTrackChanged(self):
		self.audio_track_settle_timer.stop()
		service = self.session.nav.getCurrentService()
		audioTracks = service and service.audioTracks()
		selectedAudio = audioTracks.getCurrentTrack()
		audioTracks, subtitleTracks = self.getEmbyTrackLists()
		if selectedAudio > -1:
			audio_track_obj_emby = audioTracks[selectedAudio] if audioTracks else {}
			emby_atrack_index = audio_track_obj_emby.get("Index", 0)
			if self.curAudioIndex != emby_atrack_index:
				self.curAudioIndex = emby_atrack_index
				threads.deferToThread(self.updateEmbyProgressInternal, "AudioTrackChange")
				self.audio_track_settle_checked = False
			elif not self.audio_track_settle_checked and config.plugins.e2embyclient.play_system.value in ("4097", "5002"):
				# servicehisilicon/exteplayer3 can apply the track switch
				# asynchronously, so getCurrentTrack() may still report the
				# previous track right after selectTrack() returns. Re-check
				# once more after a short settle delay before giving up.
				self.audio_track_settle_checked = True
				self.audio_track_settle_timer.start(config.plugins.e2embyclient.audio_track_change_settle_delay.value, True)
		old_subs_index = self.curSubsIndex
		if self.selected_subtitle:
			if len(self.selected_subtitle) > SUBTITLE_TUPLE_SIZE:
				self.curSubsIndex = self.selected_subtitle[3]
			else:
				sel_sub_index = self.selected_subtitle[1] - 1
				self.curSubsIndex = subtitleTracks[sel_sub_index].get("Index") if sel_sub_index > -1 else -1
		else:
			self.curSubsIndex = -1
		if old_subs_index != self.curSubsIndex:
			threads.deferToThread(self.updateEmbyProgressInternal, "SubtitleTrackChange")
		if self.is_trailer:
			self["info_line"].updateInfo(self.item, -1, -1, True)
		else:
			self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)

	def __setAudioTrack(self, aIndex):
		track = aIndex
		if isinstance(track, int) and track > -1:
			service = self.session.nav.getCurrentService()
			audioTracks = service and service.audioTracks()
			if audioTracks and audioTracks.getNumberOfTracks() > track:
				audioTracks.selectTrack(track)
				return audioTracks.getCurrentTrack() == track
		return True

	def __setSubtitleTrack(self):
		if self.CurIndexEmbeddedSubs > -1:
			service = self.session.nav.getCurrentService()
			subtitle = service and service.subtitle()
			subtitlelist = subtitle and subtitle.getSubtitleList()
			if subtitlelist:
				subtitleTrack = subtitlelist[self.CurIndexEmbeddedSubs]
				self.enableSubtitle(subtitleTrack)
			else:
				self.CurIndexEmbeddedSubs = -1
		elif self.curSubsIndex == -1:
			self.enableSubtitle(None)

	def setPlaySessionParameters(self, aIndex, sIndex, playPos=-1, stopped=False):
		item_id = self.item.get("Id")
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return
		media_source = media_sources[0]
		media_source_id = media_source.get("Id")
		EmbyApiClient.setPlaySessionParameters(self.play_session_id, item_id, media_source_id, aIndex, sIndex, playPos, stopped)

	def __getSeekableService(self):
		seek = self.getSeek()
		if seek is None or not seek.isCurrentlySeekable():
			return None
		return seek

	def __cancelSeekableWait(self):
		self.seekable_wait_timer.stop()
		self.seekable_wait_callback = None
		self.seekable_wait_elapsed = 0

	def __waitForSeekable(self, callback):
		# Poll isCurrentlySeekable() on a short interval instead of a fixed
		# delay - the backend (servicehisilicon/exteplayer3 in particular)
		# becomes seekable at an unpredictable point after evStart, and a
		# fixed delay is either a visible extra wait or a race that fires
		# too early and silently no-ops the seek/track switch.
		self.seekable_wait_callback = callback
		self.seekable_wait_elapsed = 0
		seekable = self.__getSeekableService()
		if seekable is not None:
			self.seekable_wait_callback = None
			callback(seekable)
			return
		self.seekable_wait_timer.start(self.SEEKABLE_POLL_INTERVAL, True)

	def __onSeekableWaitTick(self):
		callback = self.seekable_wait_callback
		if callback is None:
			return
		seekable = self.__getSeekableService()
		if seekable is not None:
			self.seekable_wait_callback = None
			self.seekable_wait_elapsed = 0
			callback(seekable)
			return
		self.seekable_wait_elapsed += self.SEEKABLE_POLL_INTERVAL
		if self.seekable_wait_elapsed >= self.SEEKABLE_POLL_TIMEOUT:
			self.seekable_wait_callback = None
			self.seekable_wait_elapsed = 0
			callback(None)
			return
		self.seekable_wait_timer.start(self.SEEKABLE_POLL_INTERVAL, True)

	def __cancelAudioOffsetRecheck(self):
		self.audio_offset_recheck_timer.stop()
		self.audio_offset_recheck_target = None
		self.audio_offset_recheck_last_pos = None
		self.audio_offset_recheck_stable_ms = 0
		self.audio_offset_recheck_elapsed = 0

	def __armAudioOffsetRecheck(self, target):
		# servicemp3/HiPlayer's reported position after any seek can be off
		# by a fixed amount that only settles a short, variable time after
		# the seek and stays constant until the next seek - so poll
		# getPlayPosition() until reads agree for at least
		# AUDIO_OFFSET_MIN_SETTLE_MS (or give up after SEEKABLE_POLL_TIMEOUT)
		# rather than trusting a single read right away or waiting a fixed
		# delay. The minimum settle window matters most for small/fast seeks
		# (e.g. number-key seeking) where two consecutive 50ms-apart reads
		# can coincidentally agree well before the backend actually finishes
		# recalculating its still-transitioning baseline.
		self.audio_offset_recheck_target = target
		self.audio_offset_recheck_last_pos = None
		self.audio_offset_recheck_stable_ms = 0
		self.audio_offset_recheck_elapsed = 0
		self.audio_offset_recheck_timer.start(self.SEEKABLE_POLL_INTERVAL, True)

	def __onAudioOffsetRecheckTick(self):
		target = self.audio_offset_recheck_target
		if target is None:
			return
		seekable = self.__getSeekableService()
		pos = seekable and seekable.getPlayPosition()
		reported = None if pos is None or pos[0] else pos[1] / 90000
		agreed = reported is not None and self.audio_offset_recheck_last_pos is not None and abs(reported - self.audio_offset_recheck_last_pos) < 0.5
		self.audio_offset_recheck_stable_ms = self.audio_offset_recheck_stable_ms + self.SEEKABLE_POLL_INTERVAL if agreed else 0
		settled = self.audio_offset_recheck_stable_ms >= self.AUDIO_OFFSET_MIN_SETTLE_MS
		self.audio_offset_recheck_elapsed += self.SEEKABLE_POLL_INTERVAL
		timed_out = self.audio_offset_recheck_elapsed >= self.SEEKABLE_POLL_TIMEOUT
		if settled or timed_out:
			self.__cancelAudioOffsetRecheck()
			if reported is not None:
				self.audio_pos_offset = max(0, reported - target)
			return
		self.audio_offset_recheck_last_pos = reported
		self.audio_offset_recheck_timer.start(self.SEEKABLE_POLL_INTERVAL, True)

	def __initTrackProcess(self, seekable):
		init_play_pos = -1
		if self.init_seek_to and self.init_seek_to > -1:
			init_play_pos = int(self.init_seek_to) * 10_000_000
		audioIndex, curAudioIndex, subtitle, sindex = self.getSelectedAudioSubStreamFromEmby()
		self.curAudioIndex = curAudioIndex
		self.init_audio_track_index = audioIndex
		if not self.is_audio:
			# Audio-only items have exactly one audio track and no
			# subtitles, so there's nothing to select - and selectTrack()
			# itself can re-open/re-negotiate the demux on servicemp3,
			# which is enough on its own to drop playback away from true 0.
			self.__setAudioTrack(aIndex=audioIndex)
			self.runSubtitles(subtitle=subtitle, sindex=sindex)
			if not subtitle and sindex > -1:
				self.CurIndexEmbeddedSubs = sindex
			self.curSubsIndex = subtitle and subtitle[3] or sindex
		self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)
		threads.deferToThread(self.setPlaySessionParameters, self.curAudioIndex, self.curSubsIndex, init_play_pos)
		if seekable is not None:
			self.__initSeekProcess(seekable)

	def __onInitAudioTrackSettle(self):
		# Video only - audio items never call __setAudioTrack() from
		# __initSeekProcess in the first place, so this timer is never
		# started for them (see the is_audio guard there).
		self.init_audio_track_settle_timer.stop()
		self.init_audio_track_retries += 1
		applied = self.__setAudioTrack(aIndex=self.init_audio_track_index)
		if not applied and self.init_audio_track_retries < 5:
			self.init_audio_track_settle_timer.start(config.plugins.e2embyclient.audio_track_change_settle_delay.value, True)
		else:
			# selectTrack() above can itself re-open/re-negotiate the demux on
			# servicehisilicon/exteplayer3 (same as the initial resume seek),
			# which silently resets playback back to position 0. Re-seek to
			# the resume position once more so that reopen doesn't discard it,
			# once the backend reports seekable again after the reopen. When
			# the initial seek was only the synthetic PTS-recalibration nudge
			# (no real resume position), land back on true 0 instead of the
			# nudge target - otherwise playback is left wherever the nudge
			# happened to settle, which can drift well past the intended ~1s.
			target = 0 if self.init_seek_is_nudge else self.init_seek_to
			if target is not None and target > -1:
				self.post_track_switch_seek_target = target
				self.__waitForSeekable(self.__onPostTrackSwitchSeekable)
			else:
				self.onAudioSubTrackChanged()

	def __onPostTrackSwitchSeekable(self, seekable):
		if seekable is not None:
			seekable.seekTo(int(self.post_track_switch_seek_target) * 90000)
		# Refresh curAudioIndex/info_line from what the backend actually
		# applied - the re-apply above bypasses onAudioSubTrackChanged, so
		# without this the infobar keeps showing the pre-seek track.
		self.onAudioSubTrackChanged()

	def __initSeekProcess(self, seekable):
		init_play_pos = -1
		did_seek = False
		seek_to = self.init_seek_to if self.init_seek_to and self.init_seek_to > -1 else None
		# The nudge below used to run for every fresh stream. It is a flushing
		# seek, and when it fails the pipeline is left empty and playback never
		# starts, so only seek when there is a real resume position.
		self.init_seek_is_nudge = False
		is_audio_pts_bug_case = self.is_audio and config.plugins.e2embyclient.play_system.value == "4097"
		if seek_to is not None:
			pts = int(seek_to) * 90000
			res = seekable.seekTo(pts)
			len = seekable.getLength() if config.plugins.e2embyclient.play_system.value == "5002" else [0, 1]
			if res != -1 and len[1] > 0:
				init_play_pos = int(seek_to) * 10_000_000
				did_seek = True
		if is_audio_pts_bug_case:
			# servicemp3/HiPlayer can misreport the play position by a fixed
			# amount for the entire stream after landing on any position - an
			# actual corrective seek is audible as a glitch on audio (unlike
			# the video case above), so instead measure the bogus reading once
			# the real seek (if any) above has landed, and subtract it from
			# every getPosition() read (see self.audio_pos_offset /
			# __armAudioOffsetRecheck). With no real resume position, nothing
			# was seeked above, so measure straight from true 0.
			self.__armAudioOffsetRecheck(seek_to if did_seek else 0)
		threads.deferToThread(self.setPlaySessionParameters, self.curAudioIndex, self.curSubsIndex, init_play_pos)
		if did_seek and not self.is_audio and config.plugins.e2embyclient.play_system.value in ("4097", "5002"):
			# servicehisilicon/exteplayer3 can reset the audio track back to
			# the stream default when the initial resume seek re-opens/
			# re-negotiates the demux, so the track selected right after
			# evStart gets silently overridden. Re-apply it once the resume
			# seek has actually gone through. Audio items never call
			# __setAudioTrack() in the first place (see __initTrackProcess),
			# so there's no reopen here to correct for.
			self.init_audio_track_retries = 0
			self.init_audio_track_settle_timer.start(config.plugins.e2embyclient.audio_track_change_settle_delay.value, True)

	def __onPlayerInit(self):
		pos = self.getPosition()
		if pos is not None:
			self.init_timer.stop()
			self.__evServiceStart()
			hideLoadingScreen()

	def __updatedInfoEmby(self):
		self.__setSubtitleTrack()

	def __evServiceStartInit(self):
		self.init_timer.start(50)

	def __evServiceStart(self):
		if not self.is_trailer:
			self.__waitForSeekable(self.__initTrackProcess)
		if self.progress_timer:
			self.progress_timer.start(1000)
		if not self.is_trailer:
			self.emby_progress_timer.start(10000)

	def __evServiceEnd(self):
		self.selected_subtitle = (0, 0, 0, 0, "")
		if self.progress_timer:
			self.progress_timer.stop()
		self.subtitle_renderer.stopSubtitles()
		self.emby_progress_timer.stop()
		if self.is_trailer:
			return
		last_play_pos = -1
		if self.lastPos > 0:
			# self.lastPos is whatever getPosition() last reported, which can
			# occasionally spike past the track's real length (e.g. a stale
			# audio_pos_offset reading right as playback stops) - clamp it so a
			# mid-track stop is never reported to Emby as having reached the
			# end, which would wrongly mark the item fully played.
			length = self.getLength()
			pos = min(self.lastPos, length) if length else self.lastPos
			last_play_pos = int(pos) * 10_000_000
		# Capture the outgoing item's identifiers synchronously - self.item and
		# self.play_session_id may already point at the next item (up-next
		# autoplay reuses this instance and switches self.item right after
		# this call), so a lazy self.xxx read inside the deferred thread would
		# race and report the wrong episode's stop event.
		item_id = self.item.get("Id")
		media_sources = self.item.get("MediaSources")
		media_source_id = media_sources[0].get("Id") if media_sources else None
		if media_source_id:
			threads.deferToThread(EmbyApiClient.setPlaySessionParameters, self.play_session_id, item_id, media_source_id, self.curAudioIndex, self.curSubsIndex, last_play_pos, True)

	def __playStateChanged(self, state):
		playstateString = state[3]
		if playstateString == '>':
			if not self.is_trailer:
				threads.deferToThread(self.updateEmbyProgressInternal, "Unpause")
				self.onAudioSubTrackChanged()
			self.showAfterSeek()
			self.progress_timer.start(1000)
		elif playstateString == '||':
			if not self.is_trailer:
				threads.deferToThread(self.updateEmbyProgressInternal, "Pause")
				self.onAudioSubTrackChanged()
			self.progress_timer.stop()
		elif playstateString == 'END':
			self.__evServiceEnd()
			self.progress_timer.stop()

	def clearHooks(self):
		self.audio_track_settle_timer.stop()
		self.init_audio_track_settle_timer.stop()
		self.__cancelSeekableWait()
		AudioSelection.fillSubtitleExt = None
		if self.onAudioSubTrackChanged in AudioSelection.hooks:
			AudioSelection.hooks.remove(self.onAudioSubTrackChanged)

	def handleLeave(self, what):
		hideLoadingScreen()
		self.hideSkipIntroButton()
		self.hideUpNextOverlay(dismiss=True)
		self.selected_subtitle = None
		self.is_closing = True
		if config.plugins.e2embyclient.stop_playing_service_on_load.value:
			# MoviePlayer.__onClose (base class, always runs via self.close()
			# below and can't be overridden) unconditionally calls
			# session.nav.playService(self.lastservice). Left alone, that
			# resolves/starts the original service (e.g. via the m3uiptv
			# extension hook) right here - even though it should stay stopped
			# until the whole plugin closes - and disturbs the extension's
			# state so Home's later restore of the same service no longer
			# resolves. Null it out first so the base class just stops.
			self.lastservice = None
		self.close()
		if not config.plugins.e2embyclient.stop_playing_service_on_load.value:
			self.session.nav.playService(self.lastservice)

	def leavePlayer(self):
		Globals.IsPlayingFile = False
		self.__evServiceEnd()
		self.clearHooks()
		self.handleLeave("quit")

	def leavePlayerOnExit(self):
		if self.upNextShown:
			self.hideUpNextOverlay(dismiss=True)
			return
		if self.skipIntroShown:
			self.skipIntroDismissed = True
			self.hideSkipIntroButton()
			return
		if self.is_audio:
			# The hide-then-exit-on-next-press pattern below exists so Exit
			# first hides the OSD while video keeps playing behind it - for
			# audio-only playback the OSD is kept permanently visible (see
			# updateMusicDisplay()) and there's no video to keep showing, so
			# Exit should stop playback immediately instead.
			self.leavePlayer()
			return
		if self.shown:
			self.hide()
		else:
			self.leavePlayer()

	def setResumePoint(self):
		pass

	def doEofInternal(self, playing):
		if not self.execing:
			return
		if not playing:
			return
		# This is the real end-of-stream signal (iPlayableService.evEOF, via the
		# base InfoBarSeek framework) - auto-advancing a music queue must happen
		# here, not from the 'END' playstate in __playStateChanged(), which
		# never gets a chance to run: doEofInternal() always wins the race and
		# closes the player first via handleLeave() below.
		if self.is_audio and self.hasNextQueuedTrack():
			self.playNextQueuedTrack()
			return
		# The stream can reach its actual end slightly before our estimated
		# "30s remaining" trigger fires (e.g. imprecise reported duration), so
		# fall back to autoplaying the next episode here too rather than only
		# relying on the up-next countdown - otherwise the player would just
		# quit out from under an unfinished/never-shown up-next screen.
		if config.plugins.e2embyclient.show_up_next_screen.value and self.upNextItem and not self.upNextDismissed:
			self.playUpNextItem()
			return
		self.clearHooks()
		self.handleLeave("quit")

	def up(self):
		pass

	def down(self):
		pass
