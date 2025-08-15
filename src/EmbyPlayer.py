from twisted.internet import threads
from enigma import eTimer, iPlayableService
from Screens.InfoBar import MoviePlayer
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.Sources.Progress import Progress
from Components.config import config

from .EmbyRestClient import EmbyApiClient


class EmbyPlayer(MoviePlayer):
	def __init__(self, session, service, item=None, play_session_id=None, startPos=None, slist=None, lastservice=None):
		MoviePlayer.__init__(self, session, service=service, slist=slist, lastservice=lastservice)
		self.skinName = ["EmbyPlayer", "CatchupPlayer", "MoviePlayer"]
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.init_seek_to = startPos
		self.item = item or {}
		self.play_session_id = play_session_id
		self.skip_progress_update = False
		self.current_seek_step = 0
		self.current_pos = -1
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

	def __evServiceStart(self):
		if self.init_seek_to:
			self.doSeek(int(self.init_seek_to) * 90000)
		if self.progress_timer:
			self.progress_timer.start(1000)
		threads.deferToThread(EmbyApiClient.sendStartPlaying, self.item, self.play_session_id)
		self.emby_progress_timer.start(10000)

	def __evServiceEnd(self):
		if self.progress_timer:
			self.progress_timer.stop()
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
		self.setResumePoint()
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
