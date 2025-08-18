from twisted.internet import threads
from uuid import uuid4
from enigma import eTimer, iPlayableService, eServiceReference
from Screens.InfoBar import MoviePlayer
from Screens.AudioSelection import AudioSelection
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.Sources.Progress import Progress
from Components.config import config
from requests import get, post, delete
from requests.exceptions import ReadTimeout
from Components.SystemInfo import BoxInfo

from .EmbyRestClient import EmbyApiClient
from .subrip import SubRipParser
from .TolerantDict import TolerantDict

distro = BoxInfo.getItem("distro")

SUBTITLE_TUPLE_SIZE = 6 if distro == "openatv" else 5


class EmbyPlayer(MoviePlayer):
	def __init__(self, session, item=None, startPos=None, slist=None, lastservice=None):
		item_id = int(item.get("Id", "0"))
		item_name = item.get("Name", "Stream")
		media_sources = item.get("MediaSources")
		media_source = media_sources[0]
		container = media_source.get("Container")
		media_source_id = media_source.get("Id")
		play_session_id = str(uuid4())
		directStreamUrl = f"/videos/{item_id}/original.{container}?DeviceId={EmbyApiClient.device_id}&MediaSourceId={media_source_id}&PlaySessionId={play_session_id}&api_key={EmbyApiClient.access_token}"
		url = f"{EmbyApiClient.server_root}{directStreamUrl}"
		ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % ("4097", item_id, url.replace(":", "%3a"), item_name))
		MoviePlayer.__init__(self, session, service=ref, slist=slist, lastservice=lastservice)
		self.skinName = ["EmbyPlayer", "CatchupPlayer", "MoviePlayer"]
		AudioSelection.fillSubtitleExt = self.subtitleListIject
		if self.onAudioSubTrackChanged not in AudioSelection.hooks:
			AudioSelection.hooks.append(self.onAudioSubTrackChanged)
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.curAudioIndex = -1
		self.curSubsIndex = -1
		self.firstSubIndex = -1
		self.init_seek_to = startPos
		self.item = item or {}
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
		self["progress"] = Progress()
		self["progress_summary"] = Progress()
		self["progress"].value = 0
		self["progress_summary"].value = 0
		self["time_info"] = Label("")
		self["time_elapsed"] = Label("")
		self["time_duration"] = Label("")
		self["time_remaining"] = Label("")
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
		self["NumberSeekActions"] = NumberActionMap(["NumberActions"],
		{
			"1": self.numberSeek,
			"3": self.numberSeek,
			"4": self.numberSeek,
			"6": self.numberSeek,
			"7": self.numberSeek,
			"9": self.numberSeek,
		}, -10)  # noqa: E123
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evStart: self.__evServiceStart,
			iPlayableService.evEnd: self.__evServiceEnd, })

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
		self.seek_timer.start(1000, 1)
		p += self.current_seek_step
		self.skip_progress_update = True
		self.current_pos = p
		self.setProgress(p)
		self.showAfterSeek()  # show infobar

	def onSeekRequest(self):
		self.seek_timer.stop()
		self.doSeekRelative(self.current_seek_step * 90000)
		self.current_seek_step = 0
		self.current_pos = -1
		self.skip_progress_update = False
		self.progress_timer.start(1000)
		self.updateEmbyProgress()

	def setProgress(self, pos):
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
			self["time_remaining_summary"].setText(text_remaining)
			return

		self.lastPos = pos
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
		self["time_remaining_summary"].setText(text_remaining)

	def onProgressTimer(self):
		curr_pos = self.getPosition()
		if not self.skip_progress_update:
			self.setProgress(curr_pos if self.current_pos == -1 else self.current_pos)

	def updateEmbyProgress(self):
		threads.deferToThread(self.updateEmbyProgressInternal, "TimeUpdate")

	def updateEmbyProgressInternal(self, event, pos=-1):
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
				subs_file = response.content.decode("utf-8")
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

		if self.currentSubEndPTS > -1 and currentPTS > self.currentSubEndPTS:
			self.onhideSubs()

		currentLine = None
		window_matches = self.currentSubsList.get_all_in_window(currentPTS, 150 * 90)
		if window_matches and len(window_matches) > 0:
			currentLine = window_matches[0][1]

		if currentLine and (self.currentSubPTS < 0 or self.currentSubPTS != currentLine["start"]):

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
			return

		self.enableSubtitle(None)
		subs_uri = subtitle[SUBTITLE_TUPLE_SIZE + 1]
		threads.deferToThread(self.downloadAndRunSubs, subs_uri, subtitle)

	def downloadAndRunSubs(self, subs_uri, subtitle):
		result = self.loadAndParseSubs(subs_uri)
		if result:
			self.checkSubs.start(100)
			self.selected_subtitle = subtitle
			self.curSubsIndex = subtitle[3]
			self.updateEmbyProgressInternal("SubtitleTrackChange")
		else:
			pass  # TODO: add message, log, etc...

	def subtitleListIject(self, subtitlesList):
		item_id = int(self.item.get("Id", "0"))
		media_sources = self.item.get("MediaSources")
		if not media_sources:
			return
		media_source = media_sources[0]
		media_streams = media_source.get("MediaStreams")
		i = len(subtitlesList) + 1
		for stream in media_streams:
			type_stream = stream.get("Type")
			isExternal = stream.get("IsExternal")
			if type_stream != "Subtitle" or not isExternal:
				continue
			index = int(stream.get("Index"))
			subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{index}/stream.srt?api_key={EmbyApiClient.access_token}"
			if SUBTITLE_TUPLE_SIZE == 5:
				subtitlesList.append((2, i, 4, index, stream.get("Language"), self.runSubtitles, subs_uri))
			else:
				subtitlesList.append((2, i, 4, index, stream.get("Language"), "", self.runSubtitles, subs_uri))
			i += 1

	def getSelectedAudioSubStreamFromEmby(self):
		service = self.session.nav.getCurrentService()
		subtitle = service and service.subtitle()
		subtitlelist = subtitle and subtitle.getSubtitleList()
		item_id = int(self.item.get("Id", "0"))
		media_sources = self.item.get("MediaSources")
		media_source = media_sources[0]
		media_streams = media_source.get("MediaStreams")
		defaultAudioIndex = media_source.get("DefaultAudioStreamIndex", -1)
		defaultSubtitlendex = media_source.get("DefaultSubtitleStreamIndex", -1)
		i = len(subtitlelist) + 1
		aIndex = 0
		subtitle = None
		for stream in media_streams:
			type_stream = stream.get("Type")
			index = int(stream.get("Index"))
			if type_stream == "Audio":
				if defaultAudioIndex != index:
					aIndex += 1

			isExternal = stream.get("IsExternal")
			if type_stream == "Subtitle" and self.firstSubIndex == -1:
				self.firstSubIndex = index
			if type_stream == "Subtitle" and isExternal:
				if defaultSubtitlendex == index:
					subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{index}/stream.srt?api_key={EmbyApiClient.access_token}"
					if SUBTITLE_TUPLE_SIZE == 5:
						subtitle = (2, i, 4, index, stream.get("Language"), self.runSubtitles, subs_uri)
					else:
						subtitle = (2, i, 4, index, stream.get("Language"), "", self.runSubtitles, subs_uri)
				i += 1
		return aIndex, subtitle

	def onAudioSubTrackChanged(self):
		service = self.session.nav.getCurrentService()
		audioTracks = service and service.audioTracks()
		selectedAudio = audioTracks.getCurrentTrack()
		if selectedAudio > -1:
			print(f"[EmbyPlayer] CURRENT/SELECTED AUDIO TRACK: {self.curAudioIndex} / {selectedAudio}")
			if self.curAudioIndex != selectedAudio + 1:
				self.curAudioIndex = selectedAudio + 1
				threads.deferToThread(self.updateEmbyProgressInternal, "AudioTrackChange")
		old_subs_index = self.curSubsIndex
		if self.selected_subtitle:
			if len(self.selected_subtitle) > SUBTITLE_TUPLE_SIZE:
				self.curSubsIndex = self.selected_subtitle[3]
			else:
				self.curSubsIndex = self.firstSubIndex + self.selected_subtitle[1] - 1
		else:
			self.curSubsIndex = -1
		if old_subs_index != self.curSubsIndex:
			threads.deferToThread(self.updateEmbyProgressInternal, "SubtitleTrackChange")

	def setAudioTrack(self, aIndex):
		track = aIndex
		if isinstance(track, int):
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

	def __evServiceStart(self):
		init_play_pos = -1
		if self.init_seek_to:
			self.doSeek(int(self.init_seek_to) * 90000)
			init_play_pos = int(self.init_seek_to) * 10_000_000
		self.curAudioIndex, subtitle = self.getSelectedAudioSubStreamFromEmby()
		self.setAudioTrack(aIndex=self.curAudioIndex)
		self.runSubtitles(subtitle=subtitle)
		self.curSubsIndex = subtitle and subtitle[3] or -1
		threads.deferToThread(self.setPlaySessionParameters, self.curAudioIndex, self.curSubsIndex, init_play_pos)
		if self.progress_timer:
			self.progress_timer.start(1000)
		self.emby_progress_timer.start(10000)

	def __evServiceEnd(self):
		self.currentSubPTS = -1
		self.currentSubsList = TolerantDict({})
		self.selected_subtitle = (0, 0, 0, 0, "")
		if self.progress_timer:
			self.progress_timer.stop()
		self.checkSubs.stop()
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
			self.progress_timer.start(1000)
		elif playstateString == '||':
			threads.deferToThread(self.updateEmbyProgressInternal, "Pause")
			self.onAudioSubTrackChanged()
			self.progress_timer.stop()
		elif playstateString == 'END':
			self.progress_timer.stop()

	def clearHooks(self):
		AudioSelection.fillSubtitleExt = None
		if self.onAudioSubTrackChanged in AudioSelection.hooks:
			AudioSelection.hooks.remove(self.onAudioSubTrackChanged)

	def leavePlayer(self):
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
