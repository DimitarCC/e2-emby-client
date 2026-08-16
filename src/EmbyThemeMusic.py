from twisted.internet import threads

from enigma import eServiceReference, eTimer, eServiceCenter
from Components.config import config

from .EmbyRestClient import EmbyApiClient

_playing_service = None
_playing_song_id = None
_playing_owners = []


class _PlaybackStarter:
	# Mirrors plugin.py's _ServiceRestorer cadence: stopService() on the theme
	# song's audio-only service returns before the GStreamer pipeline (its
	# dvbaudiosink) has actually torn down. Starting the next stream's pipeline
	# immediately races that teardown and can fail with "Could not determine
	# type of stream" from the still-releasing dvbaudiosink. So poll until
	# Navigation confirms nothing is playing, then wait a further grace period
	# before starting the next stream, since dvbaudiosink can still be
	# finalizing even after getCurrentlyPlayingServiceReference() goes None.
	MAX_ATTEMPTS = 14
	RETRY_DELAY = 300  # ms

	def __init__(self, session, start_fn):
		self.session = session
		self.start_fn = start_fn
		self.attempts = 0
		self.settled = False
		self.timer = eTimer()
		self.timer.callback.append(self.__attempt)
		self.timer.start(0, True)  # check right away - the settle delay below is what actually needs to wait

	def __attempt(self):
		if not self.settled:
			if self.session.nav.getCurrentlyPlayingServiceReference() is not None:
				self.attempts += 1
				if self.attempts < self.MAX_ATTEMPTS:
					self.timer.start(self.RETRY_DELAY, True)
					return
			self.settled = True
			self.timer.start(config.plugins.e2embyclient.theme_music_settle_delay.value, True)
			return
		self.start_fn()


def _buildThemeSongRef(song):
	song_id = int(song.get("Id", "0"))
	media_sources = song.get("MediaSources", [])
	container = media_sources[0].get("Container") if media_sources else "mp3"
	url = f"{EmbyApiClient.server_root}/audio/{song_id}/stream.{container}?static=true&api_key={EmbyApiClient.access_token}&DeviceId={EmbyApiClient.device_id}"
	name = song.get("Name", "Theme")
	return eServiceReference("%s:0:2:%x:1011:1:CCCC0000:0:0:0:%s:%s" % (config.plugins.e2embyclient.play_system.value, song_id, url.replace(":", "%3a"), name))


def _startThemeMusic(songs, owner):
	global _playing_service, _playing_song_id
	if not songs:
		return
	song = songs[0]
	song_id = song.get("Id")
	if _playing_song_id == song_id and _playing_service is not None:
		# Same theme already playing (e.g. inherited from a parent series screen
		# still open below us) - just register as another interested screen,
		# regardless of which one's lookup happened to resolve first.
		if not any(owner is o for o in _playing_owners):
			_playing_owners.append(owner)
		return
	# stopThemeMusic()
	ref = _buildThemeSongRef(song)
	service = eServiceCenter.getInstance().play(ref)
	if service and service.start() == 0:
		_playing_service = service
		_playing_song_id = song_id
		_playing_owners.append(owner)


def playThemeMusicForItem(item_id, owner):
	if not (config.plugins.e2embyclient.stop_playing_service_on_load.value and config.plugins.e2embyclient.play_theme_music.value):
		return
	threads.deferToThread(EmbyApiClient.getThemeSongs, item_id).addCallback(lambda songs: _startThemeMusic(songs, owner))


def stopThemeMusic():
	global _playing_service, _playing_song_id
	if _playing_service is not None:
		_playing_service.stop()
	_playing_service = None
	_playing_song_id = None
	_playing_owners.clear()


def stopThemeMusicThenPlay(session, start_fn):
	"""Stop theme music (if playing) and only call start_fn once Navigation
	confirms the service is actually released (plus a settle delay), to avoid
	racing the next stream's GStreamer pipeline against the theme song's
	teardown."""
	was_playing = _playing_service is not None
	if not was_playing:
		start_fn()
		return
	stopThemeMusic()
	_PlaybackStarter(session, start_fn)


def stopThemeMusicIfOwner(owner):
	for i, o in enumerate(_playing_owners):
		if o is owner:
			del _playing_owners[i]
			if not _playing_owners:
				stopThemeMusic()
			break
