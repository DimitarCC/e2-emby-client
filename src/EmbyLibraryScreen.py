import uuid
from twisted.internet import threads
from enigma import eServiceReference
from Screens.Screen import Screen
from Screens.InfoBar import InfoBar
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap

from .EmbyGridList import EmbyGridList
from .EmbyRestClient import EmbyApiClient
from .EmbyPlayer import EmbyPlayer

class E2EmbyLibrary(Screen):
	skin = ["""<screen name="E2EmbyLibrary" position="fill">
					<widget name="list" position="40,0" size="e-80,e" iconWidth="200" iconHeight="260" spacing="10" scrollbarMode="showNever" transparent="1" />
				</screen>"""]  # noqa: E124

	def __init__(self, session, library_id):
		Screen.__init__(self, session)
		self.library_id = library_id
		self.boxsets = []
		self.movies = []
		self.setTitle(_("Emby Library"))
		self["list"] = EmbyGridList()
		self.onShown.append(self.__onShown)

		self["actions"] = ActionMap(["E2EmbyActions",],
			{
				"cancel": self.close,  # KEY_RED / KEY_EXIT
				# "save": self.addProvider,  # KEY_GREEN
				"ok": self.processItem,
				# "yellow": self.keyYellow,
				# "blue": self.clearData,
			}, -1)

	def __onShown(self):
		threads.deferToThread(self.loadItems)

	def processItem(self):
		selected_item = self["list"].getCurrentItem()
		infobar = InfoBar.instance
		if infobar:
			LastService = self.session.nav.getCurrentServiceReferenceOriginal()
			item_id = int(selected_item.get("Id", "0"))
			item_name = selected_item.get("Name", "Stream")
			play_session_id = str(uuid.uuid4())
			startTimeTicks = int(selected_item.get("UserData", {}).get("PlaybackPositionTicks", "0")) / 10_000_000
			# subs_uri = f"{EmbyApiClient.server_root}/emby/Items/{item_id}/mediasource_80606/Subtitles/21/stream.srt?api_key={EmbyApiClient.access_token}"
			url = f"{EmbyApiClient.server_root}/emby/Videos/{item_id}/stream?api_key={EmbyApiClient.access_token}&PlaySessionId={play_session_id}&DeviceId={EmbyApiClient.device_id}&static=true&EnableAutoStreamCopy=false"
			ref = eServiceReference("%s:0:1:%x:1009:1:CCCC0000:0:0:0:%s:%s" % ("4097", item_id, url.replace(":", "%3a"), item_name))
			self.session.open(EmbyPlayer, ref, startPos=startTimeTicks, slist=infobar.servicelist, lastservice=LastService)

	def loadItems(self):
		items = EmbyApiClient.getItemsFromLibrary(self.library_id)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list"].loadData(list)	
