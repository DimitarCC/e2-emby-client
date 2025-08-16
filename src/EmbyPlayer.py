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
		play_session_id = str(uuid4())
		media_sources = item.get("MediaSources")
		media_source = media_sources[0]
		defaultAudio_idx = media_source.get("DefaultAudioStreamIndex", -1)
		defaultSubtitle_idx = media_source.get("DefaultSubtitleStreamIndex", -1)
		subs_uri = ""
		# if defaultSubtitle_idx > -1:
		# 	subs_uri = f"&suburi={EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{defaultSubtitle_idx}/stream.srt?api_key={EmbyApiClient.access_token}"
		tracks_addon = ""
		if defaultAudio_idx > -1:
			tracks_addon += f"&AudioStreamIndex={defaultAudio_idx}"
		if defaultSubtitle_idx > -1:
			tracks_addon += f"&SubtitleStreamIndex={defaultSubtitle_idx}"
		url = f"{EmbyApiClient.server_root}/emby/Videos/{item_id}/stream?api_key={EmbyApiClient.access_token}&PlaySessionId={play_session_id}&DeviceId={EmbyApiClient.device_id}&static=true&EnableAutoStreamCopy=false{tracks_addon}{subs_uri.replace(":", "%3a")}"
		ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % ("4097", item_id, url.replace(":", "%3a"), item_name))
		MoviePlayer.__init__(self, session, service=ref, slist=slist, lastservice=lastservice)
		self.skinName = ["EmbyPlayer", "CatchupPlayer", "MoviePlayer"]
		AudioSelection.fillSubtitleExt = self.subtitleListIject
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.init_seek_to = startPos
		self.item = item or {}
		self.play_session_id = play_session_id
		self.skip_progress_update = False
		self.current_seek_step = 0
		self.current_pos = -1
		self.selectedSubtitleTrack = (0, 0, 0, 0, "und")
		self.current_subs_stream = defaultSubtitle_idx
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
		self.onProgressTimer()
		self.seek_timer = eTimer()
		self.seek_timer.callback.append(self.onSeekRequest)
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

	def updateEmbyProgress(self):
		pos = self.getPosition()
		ticks = pos * 10_000_000
		threads.deferToThread(EmbyApiClient.sendPlayingProgress, self.item, ticks, self.play_session_id)

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

	def runSubtitles(self, subtitle):
		if not subtitle:
			self.checkSubs.stop()
			self.currentSubPTS = -1
			self.currentSubsList = TolerantDict({})
			self.selected_subtitle = (0, 0, 0, 0, "")
			return

		self.enableSubtitle(None)
		subs_uri = subtitle[SUBTITLE_TUPLE_SIZE + 1]
		threads.deferToThread(self.downloadAndRunSubs, subs_uri, subtitle)

	def downloadAndRunSubs(self, subs_uri, subtitle):
		result = self.loadAndParseSubs(subs_uri)
		if result:
			self.checkSubs.start(100)
			self.selected_subtitle = subtitle
		else:
			pass  # TODO: add message, log, etc...

	def subtitleListIject(self, subtitlesList):
		item_id = int(self.item.get("Id", "0"))
		media_sources = self.item.get("MediaSources")
		media_source = media_sources[0]
		media_streams = media_source.get("MediaStreams")
		i = len(subtitlesList) + 1
		for stream in media_streams:
			type_stream = stream.get("Type")
			isExternal = stream.get("IsExternal")
			if type_stream != "Subtitle" or not isExternal:
				continue
			index = stream.get("Index")
			subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{index}/stream.srt?api_key={EmbyApiClient.access_token}"
			if SUBTITLE_TUPLE_SIZE == 5:
				subtitlesList.append((2, i, 4, 0, stream.get("Language"), self.runSubtitles, subs_uri))
			else:
				subtitlesList.append((2, i, 4, 0, stream.get("Language"), "", self.runSubtitles, subs_uri))
			i += 1

	def __evServiceStart(self):

		if self.init_seek_to:
			self.doSeek(int(self.init_seek_to) * 90000)
		# item_id = int(self.item.get("Id", "0"))
		# media_sources = self.item.get("MediaSources")
		# media_source = media_sources[0]
		# subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/21/stream.srt?api_key={EmbyApiClient.access_token}"
		# self.loadAndParseSubs(subs_uri)
		# self.checkSubs.start(100)

		# service = self.session.nav.getCurrentService()
		# subtitle = service and service.subtitle()
		# if subtitle:
		# 	item_id = int(self.item.get("Id", "0"))
		# 	media_sources = self.item.get("MediaSources")
		# 	media_source = media_sources[0]
		# 	media_streams = media_source.get("MediaStreams")
		# 	for stream in media_streams:
		# 		type_stream = stream.get("Type")
		# 		isExternal = stream.get("IsExternal")
		# 		if type_stream != "Subtitle" or not isExternal:
		# 			continue
		# 		index = stream.get("Index")
		# 		subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/{media_source.get("Id")}/Subtitles/{index}/stream.srt?api_key={EmbyApiClient.access_token}"
		# 		subtitle.addExternalSubtitles((4,1,4,0,"bg", subs_uri, "UTF-8"))
		# if self.selectedSubtitleTrack:
		# 	self.changeSubTimer.start(1000, True)
		# else:
		# 	self.enableSubtitleTrack(None)
		if self.progress_timer:
			self.progress_timer.start(1000)
		threads.deferToThread(EmbyApiClient.sendStartPlaying, self.item, self.play_session_id)
		self.emby_progress_timer.start(10000)

	def __evServiceEnd(self):
		self.currentSubPTS = -1
		self.currentSubsList = TolerantDict({})
		self.selected_subtitle = (0, 0, 0, 0, "")
		if self.progress_timer:
			self.progress_timer.stop()
		self.checkSubs.stop()
		threads.deferToThread(EmbyApiClient.sendStopPlaying, self.item, self.play_session_id)
		self.emby_progress_timer.stop()

	def __playStateChanged(self, state):
		playstateString = state[3]
		if playstateString == '>':
			self.progress_timer.start(1000)
		elif playstateString == '||':
			self.progress_timer.stop()
		elif playstateString == 'END':
			self.progress_timer.stop()

	def leavePlayer(self):
		AudioSelection.fillSubtitleExt = None
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

		self.handleLeave("quit")

	def up(self):
		pass

	def down(self):
		pass
