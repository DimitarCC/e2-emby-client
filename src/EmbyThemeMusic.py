from twisted.internet import threads

from enigma import eServiceReference, eServiceCenter
from Components.config import config

from .EmbyRestClient import EmbyApiClient

_playing_service = None
_playing_song_id = None
_playing_owners = []


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
	stopThemeMusic()
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


def stopThemeMusicIfOwner(owner):
	for i, o in enumerate(_playing_owners):
		if o is owner:
			del _playing_owners[i]
			if not _playing_owners:
				stopThemeMusic()
			break
