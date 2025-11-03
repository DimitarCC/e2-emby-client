# coding: utf-8

from requests import get, post, delete
from requests.exceptions import ReadTimeout
from uuid import uuid4

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
from Tools.LoadPixmap import LoadPixmap

from .EmbyInfoLine import EmbyInfoLine
from .EmbyList import EmbyList
from .EmbyPlayerInfobarInfo import EmbyPlayerInfobarInfo
from .EmbyRestClient import EmbyApiClient
from .HelperFunctions import convert_ticks_to_time
from .subrip import SubRipParser
from .TolerantDict import TolerantDict
from .Variables import SUBTITLE_TUPLE_SIZE, EMBY_THUMB_CACHE_DIR
from .Globals import IsPlayingFile

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


class EmbyPlayer(MoviePlayer):
	skin = ["""<screen name="EmbyPlayer" position="fill" flags="wfNoBorder" backgroundColor="#ff000000">
					<widget name="info_line" position="240,954" size="e-40-240,45" font="Regular; 35" fontAdditional="Bold;24" transparent="1" zPosition="5"/>
					<widget name="info_bkg" backgroundColor="#10111111" position="-2,540" zPosition="-1" size="e+4,315" widgetBorderWidth="1" widgetBorderColor="#444444" />
		 			<widget name="poster" backgroundColor="#10111111" position="30,557" zPosition="2" size="187,280" cornerRadius="6" widgetBorderWidth="1" widgetBorderColor="#444444" scale="1" />
					<widget name="list_chapters" position="35,560" size="e-70,310" iconWidth="340" iconHeight="188" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" transparent="1"/>
		 			<widget name="info_panel_line" position="275,560" size="e-340,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="275,630" size="e-340,230" alphatest="blend" font="Regular;30" transparent="1"/>
					<eLabel backgroundColor="#10111111" position="60,900" zPosition="-1" size="e-120,115" cornerRadius="8" widgetBorderWidth="1" widgetBorderColor="#444444" />
					<widget name="statusicon" position="120,935" zPosition="3" size="48,48" scale="1" pixmaps="icons/pvr/play.svg,icons/pvr/pause.svg,icons/pvr/stop.svg,icons/pvr/ff.svg,icons/pvr/rew.svg,icons/pvr/slow.svg"/>
					<widget name="speed" foregroundColor="white" halign="left" position="200,935" size="48,48" font="Bold; 24" transparent="1"/>
					<widget name="time_elapsed" position="210,905" size="100,51" font="Bold; 26" halign="right" valign="center" backgroundColor="#02111111" transparent="1" foregroundColor="#ffffff"/>
					<widget name="time_remaining_total" position="e-270-10,905" size="200,51" font="Bold; 26" halign="right" valign="center" backgroundColor="#02111111" transparent="1" foregroundColor="#ffffff"/>
					<widget source="progress" render="Progress" backgroundColor="#02333333" foregroundColor="#32772b" position="340,925" zPosition="2" size="e-260-340,12" transparent="1" cornerRadius="6"/>
				</screen>"""]

	def __init__(self, session, item=None, startPos=None, slist=None, lastservice=None, is_trailer=False):
		IsPlayingFile = True
		item_id = int(item.get("Id", "0"))
		item_name = item.get("Name", "Stream")
		media_sources = item.get("MediaSources")
		ref = None
		play_session_id = ""
		if media_sources and not is_trailer:
			media_source = media_sources[0]
			defaultAudioIndex = media_source.get("DefaultAudioStreamIndex", -1)
			defaultSubtitleIndex = media_source.get("DefaultSubtitleStreamIndex", -1)
			container = media_source.get("Container")
			media_source_id = media_source.get("Id")
			play_session_id = str(uuid4())
			directStreamUrl = f"/videos/{item_id}/original.{container}?DeviceId={EmbyApiClient.device_id}&MediaSourceId={media_source_id}&PlaySessionId={play_session_id}&api_key={EmbyApiClient.access_token}"
			url = f"{EmbyApiClient.server_root}{directStreamUrl}"
			ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % (config.plugins.e2embyclient.play_system.value, item_id, url.replace(":", "%3a"), item_name))
		if is_trailer and YoutubeDL:
			trailers = item.get("RemoteTrailers", [])
			if trailers:
				trailer = trailers[0]
				url_trailer = trailer.get("Url", "").strip()
				if url_trailer and "youtube" in url_trailer:
					try:
						ydl = YoutubeDL({"format": "b", "no_color": True, "usenetrc": True})
						result = ydl.extract_info(url_trailer, download=False)
						result = ydl.sanitize_info(result)
						if result and result.get("url"):
							url = result["url"].strip()
							ref = eServiceReference("%s:0:1:%x:1010:1:CCCC0000:0:0:0:%s:%s" % (config.plugins.e2embyclient.play_system.value, item_id, url.replace(":", "%3a"), f"Trailer - {item_name}"))
					except Exception as e:
						print(f" failed {e}")
		MoviePlayer.__init__(self, session, service=ref, slist=slist, lastservice=lastservice)
		self.session = session
		self.is_trailer = is_trailer
		AudioSelection.fillSubtitleExt = self.subtitleListIject
		if self.onAudioSubTrackChanged not in AudioSelection.hooks:
			AudioSelection.hooks.append(self.onAudioSubTrackChanged)
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.onHide.append(self.__onHide)
		self.init_seek_to = startPos
		self.curAudioIndex = -1
		self.curSubsIndex = -1
		self.firstSubIndex = -1
		self.supressChapterSelect = False
		self.item = item or {}
		self.chapters = []
		self.play_session_id = play_session_id
		self.skip_progress_update = False
		self.current_seek_step = 0
		self.current_pos = -1
		self.lastPos = -1
		self.selectedSubtitleTrack = (0, 0, 0, 0, "und")
		self.subs_parser = SubRipParser()
		self.currentSubsList = TolerantDict({})
		self.currentSubPTS = -1
		self.currentSubEndPTS = -1
		self.selected_widget = None
		self["poster"] = Pixmap()
		self["poster"].hide()
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
		self.progress_timer = eTimer()
		self.progress_timer.callback.append(self.onProgressTimer)
		self.checkSubs = eTimer()
		self.checkSubs.callback.append(self.checkPTSAndShowSub)
		self.hideSubs = eTimer()
		self.hideSubs.callback.append(self.onhideSubs)
		self.emby_progress_timer = eTimer()
		self.emby_progress_timer.callback.append(self.updateEmbyProgress)
		self.seek_timer = eTimer()
		self.seek_timer.callback.append(self.onSeekRequest)
		self.onProgressTimer()
		if is_trailer:
			self["info_line"].updateInfo(self.item, -1, -1)
		else:
			self["info_line"].updateInfo(self.item, defaultAudioIndex, defaultSubtitleIndex)
		self["info_panel_line"].updateInfo(self.item)
		self.loadChapters()
		self.info_shown = False
		self["NumberSeekActions"] = NumberActionMap(["NumberActions"],
		{
			"1": self.numberSeek,
			"3": self.numberSeek,
			"4": self.numberSeek,
			"6": self.numberSeek,
			"7": self.numberSeek,
			"9": self.numberSeek,
		}, -10)
		self["InfobarMovieActions"] = ActionMap(["InfobarMovieListActions", "MovieSelectionActions", "E2EmbyActions"],
		{
			"up": self.showChapters,
			"down": self.showNextPlaylist,
			"movieList": self.showChapters,
			"showEventInfo": self.showInfo,
			"ok": self.processItem,
		}, -10)
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: self.__evServiceStart, })

	def __onHide(self):
		self["list_chapters"].hide()
		self["info_bkg"].hide()
		self["poster"].hide()
		self["info_panel_line"].hide()
		self["plot"].hide()
		self.selected_widget = None
		self.info_shown = False
		self.supressChapterSelect = False

	def loadChapters(self):
		if self.is_trailer:
			return
		media_sources = self.item.get("MediaSources", [])
		default_media_source = next((ms for ms in media_sources if ms.get("Type") == "Default"), None)
		if default_media_source:
			self.chapters = default_media_source.get("Chapters", [])

	def seekBack(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekBack(self)
		self.showAfterSeek()

	def left(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveLeft)

	def seekFwd(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekFwd(self)
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekFwdManual(self, fwd=True):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekFwdManual(self, fwd)
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekBackManual(self, fwd=False):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekBackManual(self, fwd)
		self.showAfterSeek()
		self.hideTimer.stop()

	def seekBackSeekbar(self, fwd=False):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekBackSeekbar(self, fwd)

	def seekFwdSeekbar(self, fwd=True):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekFwdSeekbar(self, fwd)

	def seekFwdVod(self, fwd=True):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			return
		MoviePlayer.seekFwdVod(self, fwd)

	def right(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			self.supressChapterSelect = True
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].moveRight)

	def processItem(self):
		if self.selected_widget and self.selected_widget == "list_chapters":
			chapter = self["list_chapters"].selectedItem
			startPos = int(chapter.get("StartPositionTicks", "0")) / 10_000_000
			self.doSeek(int(startPos) * 90000)
			self.showAfterSeek()
		else:
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
		if self.is_trailer:
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
		return pos[1] / 90000

	def numberSeek(self, key):
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
		curr_pos = self.getPosition()
		if not self.skip_progress_update:
			self.setProgress(curr_pos if self.current_pos == -1 else self.current_pos)
		if self.selected_widget == "list_chapters" and not self.supressChapterSelect:
			cur_ch_index = self.find_current_chapter_index()
			if cur_ch_index != self["list_chapters"].getCurrentIndex():
				self["list_chapters"].instance.moveSelectionTo(cur_ch_index)

	def updateEmbyProgress(self):
		if self.is_trailer:
			return
		threads.deferToThread(self.updateEmbyProgressInternal, "TimeUpdate", self.current_pos)

	def updateEmbyProgressInternal(self, event, pos=-1):
		if self.is_trailer:
			return
		if pos == -1:
			pos = self.getPosition()
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
				self.currentSubsList = TolerantDict(self.subs_parser.parse(subs_file))
				return True
		except:
			pass
		return False

	def checkPTSAndShowSubBase(self):
		seek = self.getSeek()
		if seek is None:
			return
		pos = seek.getPlayPosition()
		currentPTS = int(pos[1])

		if self.currentSubEndPTS > -1 and currentPTS >= self.currentSubEndPTS:
			self.onhideSubs()

		currentLine = None
		window_matches = self.currentSubsList.get_all_in_window(currentPTS, 150 * 90)
		if window_matches and len(window_matches) > 0:
			currentLine = window_matches[0][1]

		if currentLine and (self.currentSubPTS < 0 or self.currentSubPTS != currentLine["start"]) and currentPTS >= currentLine["start"]:
			self.currentSubPTS = currentLine["start"]
			self.currentSubEndPTS = currentLine["end"]
			subtitleText = currentLine["text"]
			self.subtitle_window.showSubtitles(subtitleText)

	def onhideSubs(self):
		self.currentSubEndPTS = -1
		self.subtitle_window.showSubtitles("")
		self.subtitle_window.hideSubtitles()

	def checkPTSAndShowSub(self):
		self.checkPTSAndShowSubBase()

	def runSubtitles(self, subtitle):
		if not subtitle:
			self.checkSubs.stop()
			self.currentSubPTS = -1
			self.currentSubsList = TolerantDict({})
			self.selected_subtitle = (0, 0, 0, 0, "")
			self.curSubsIndex = -1
			self.updateEmbyProgressInternal("SubtitleTrackChange")
			self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)
			return

		self.enableSubtitle(None)
		subs_uri = subtitle[SUBTITLE_TUPLE_SIZE + 1]
		threads.deferToThread(self.downloadAndRunSubs, subs_uri, subtitle)

	def downloadAndRunSubs(self, subs_uri, subtitle):
		result = self.loadAndParseSubs(subs_uri)
		if result:
			self.checkSubs.start(10)
			self.selected_subtitle = subtitle
			self.curSubsIndex = subtitle[3]
			self.updateEmbyProgressInternal("SubtitleTrackChange")
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

		return aIndex, curAudioIndex, subtitle

	def onAudioSubTrackChanged(self):
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
			self["info_line"].updateInfo(self.item, -1, -1)
		else:
			self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)

	def setAudioTrack(self, aIndex):
		track = aIndex
		if isinstance(track, int) and track > -1:
			service = self.session.nav.getCurrentService()
			audioTracks = service and service.audioTracks()
			ref = self.session.nav.getCurrentServiceReferenceOriginal()
			ref = ref and eServiceReference(ref)
			if audioTracks.getNumberOfTracks() > track:
				audioTracks.selectTrack(track)

	def setPlaySessionParameters(self, aIndex, sIndex, playPos=-1, stopped=False):
		item_id = self.item.get("Id")
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return
		media_source = media_sources[0]
		media_source_id = media_source.get("Id")
		EmbyApiClient.setPlaySessionParameters(self.play_session_id, item_id, media_source_id, aIndex, sIndex, playPos, stopped)

	def initSeekProcess(self):
		init_play_pos = -1
		audioIndex, curAudioIndex, subtitle = self.getSelectedAudioSubStreamFromEmby()
		self.setAudioTrack(aIndex=audioIndex)
		self.curAudioIndex = curAudioIndex
		self.runSubtitles(subtitle=subtitle)
		self.curSubsIndex = subtitle and subtitle[3] or -1
		self["info_line"].updateInfo(self.item, self.curAudioIndex, self.curSubsIndex)
		if self.init_seek_to and self.init_seek_to > -1:
			self.doSeek(int(self.init_seek_to) * 90000)
			init_play_pos = int(self.init_seek_to) * 10_000_000
		threads.deferToThread(self.setPlaySessionParameters, self.curAudioIndex, self.curSubsIndex, init_play_pos)

	def __evServiceStart(self):
		if not self.is_trailer:
			self.initSeekProcess()
		if self.progress_timer:
			self.progress_timer.start(1000)
		if not self.is_trailer:
			self.emby_progress_timer.start(10000)

	def __evServiceEnd(self):
		self.currentSubPTS = -1
		self.currentSubsList = TolerantDict({})
		self.selected_subtitle = (0, 0, 0, 0, "")
		if self.progress_timer:
			self.progress_timer.stop()
		self.checkSubs.stop()
		if self.is_trailer:
			return
		last_play_pos = -1
		if self.lastPos > 0:
			last_play_pos = int(self.lastPos) * 10_000_000
		threads.deferToThread(self.setPlaySessionParameters, self.curAudioIndex, self.curSubsIndex, last_play_pos, True)
		self.emby_progress_timer.stop()

	def __playStateChanged(self, state):
		playstateString = state[3]
		if playstateString == '>':
			threads.deferToThread(self.updateEmbyProgressInternal, "Unpause")
			self.onAudioSubTrackChanged()
			self.showAfterSeek()
			self.progress_timer.start(1000)
		elif playstateString == '||':
			threads.deferToThread(self.updateEmbyProgressInternal, "Pause")
			self.onAudioSubTrackChanged()
			self.progress_timer.stop()
		elif playstateString == 'END':
			self.__evServiceEnd()
			self.progress_timer.stop()

	def clearHooks(self):
		AudioSelection.fillSubtitleExt = None
		if self.onAudioSubTrackChanged in AudioSelection.hooks:
			AudioSelection.hooks.remove(self.onAudioSubTrackChanged)

	def leavePlayer(self):
		IsPlayingFile = False
		self.__evServiceEnd()
		self.clearHooks()
		self.handleLeave("quit")

	def leavePlayerOnExit(self):
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

		self.clearHooks()
		self.handleLeave("quit")

	def up(self):
		pass

	def down(self):
		pass
