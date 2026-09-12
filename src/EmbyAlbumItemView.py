from twisted.internet import threads
from Components.Label import Label
from Components.Pixmap import Pixmap
from Tools.LoadPixmap import LoadPixmap

from .EmbyItemViewBase import EmbyItemViewBase
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyItemFunctionButtons import playQueue
from .EmbyLoadingScreen import showLoadingScreen
from .EmbyRestClient import EmbyApiClient
from .HelperFunctions import insert_at_position, create_thumb_cache_dir
from . import _


COVER_SIZE = 500  # keep in sync with the "cover" widget's skin size below
COVER_WIDGET_ID = "album_cover"  # dedicated thumb-cache subfolder for loadCover()


class EmbyAlbumItemView(EmbyItemViewBase):
	supportsThemeMusic = False

	skin = ["""<screen name="EmbyAlbumItemView" position="fill">
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="cover" backgroundColor="#10111111" position="60,60" zPosition="1" size="500,500" cornerRadius="10" widgetBorderWidth="1" widgetBorderColor="#444444" scale="1" alphaBlend="1"/>
					<widget name="title_logo" position="600,60" size="e-660,80" alphatest="blend"/>
					<widget name="title" position="600,60" size="e-660,80" alphatest="blend" font="Bold;56" transparent="1" noWrap="1"/>
					<widget name="infoline" position="600,150" size="e-660,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="600,220" size="e-660,150" alphatest="blend" font="Regular;28" transparent="1"/>
					<widget name="f_buttons" position="600,390" size="e-660,65" font="Regular;32" transparent="1"/>
					<widget name="tracks_header" position="600,480" size="e-660,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="tracks_list" position="600,530" listOrientation="vertical" size="e-660,e-590" font="Regular;24" scrollbarMode="showOnDemand" transparent="1"/>
				</screen>"""]  # noqa: E101

	def __init__(self, session, item, backdrop=None, logo=None):
		EmbyItemViewBase.__init__(self, session, item, backdrop, logo)
		self.album_id = self.item_id
		self.tracks = []
		# PrimaryImageItemId/PrimaryImageTag (not ImageTags.Primary) is the
		# reliable source for a MusicAlbum's own cover - capture it here,
		# before loadItemInfoFromServer() overwrites self.item with a fresh
		# getSingleItem() fetch.
		self.cover_item_id = item.get("PrimaryImageItemId")
		self.cover_tag = item.get("PrimaryImageTag")
		self["cover"] = Pixmap()
		self["tracks_header"] = Label(_("Tracks"))
		self["tracks_list"] = EmbyList(type="tracks")
		self.tracks_controller = EmbyListController(self["tracks_list"], self["tracks_header"])
		self.lists = insert_at_position(self.lists, "tracks_list", self.tracks_controller, 0)
		self.availableWidgets.append("tracks_list")

	def loadItemDetails(self, item, backdrop_pix):
		# Deliberately does not call EmbyItemViewBase.loadItemDetails(): its
		# title/logo handling reads ImageTags.Logo/ParentLogoImageTag, which
		# for a MusicAlbum can resolve to inherited artist branding art (Emby's
		# "parent" for a music album's inherited images is the artist, not a
		# folder) - showing the artist's logo/name where the album's own title
		# belongs. Always show the album's own name as plain text instead, and
		# load its own cover art (there's no backdrop concept for an album).
		self["title"].text = " ".join(item.get("Name", "").splitlines())
		self["title_logo"].setPixmap(None)
		self["infoline"].updateInfo(item)
		self.infoRetrieveInject(item=item)
		self["plot"].text = item.get("Overview", "")
		threads.deferToThread(self.loadCover)
		self.injectAfterLoad(item)

	def loadCover(self):
		item_id = self.cover_item_id
		icon_img = self.cover_tag
		if not icon_img:
			item_id = self.item.get("PrimaryImageItemId")
			icon_img = self.item.get("PrimaryImageTag")
		if not icon_img:
			self["cover"].setPixmap(None)
			return
		# getItemImage() writes into a per-widget_id thumb-cache subfolder that
		# only EmbyList/EmbyGridList/EmbyMusicRowList normally pre-create in
		# their postWidgetCreate() - this screen's cover is a plain Pixmap, so
		# create its own subfolder here or the write can fail silently (no
		# cover shown) whenever thumbcache_loc is "off" or "/tmp".
		create_thumb_cache_dir(COVER_WIDGET_ID)
		pix_path = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, max_width=COVER_SIZE, max_height=COVER_SIZE, image_type="Primary", widget_id=COVER_WIDGET_ID)
		pix = pix_path and LoadPixmap(pix_path)
		if pix and self["cover"].instance:
			self["cover"].setPixmap(pix)
			self["cover"].show()

	def getTracks(self):
		self.tracks = EmbyApiClient.getTracksForAlbum(self.album_id)
		list = []
		if self.tracks:
			i = 0
			for track in self.tracks:
				played_perc = track.get("UserData", {}).get("PlayedPercentage", "0")
				title = f"{track.get('IndexNumber', i + 1)}. {" ".join(track.get("Name", "").splitlines())}"
				list.append((i, track, title, None, played_perc, True))
				i += 1
			self["tracks_list"].loadData(list)

	def infoRetrieveInject(self, item):
		threads.deferToThread(self.getTracks).addCallback(self.onLayoutFinishedLast)

	def playAlbumFromTrack(self, start_index):
		if not self.tracks:
			return
		showLoadingScreen(self.session)
		start_pos = int(self.tracks[start_index].get("UserData", {}).get("PlaybackPositionTicks", "0")) / 10_000_000
		playQueue(self.tracks, start_index, self.session, self.playerExitCallback, startPos=start_pos)

	def playerExitCallback(self, *result):
		self.loadItemInUI(self.loadItemInfoFromServer(self.item_id))
		self.onLayoutFinishedLast()
		self.selected_widget = "f_buttons"
		self["f_buttons"].enableSelection(True)

	def processItem(self):
		EmbyItemViewBase.processItem(self)
		if self.selected_widget == "tracks_list":
			start_index = self["tracks_list"].selectedIndex
			self.playAlbumFromTrack(start_index)

	def onLayoutFinishedLast(self, result=None):
		# The base implementation re-stacks every list in self.lists at a
		# shared x position, one below another - built for the old layout
		# where content lists were full-width filmstrips under f_buttons. This
		# screen instead has a single fixed-position tracks_list living beside
		# the cover art (see skin), so just show/hide + selection-enable it in
		# place rather than letting the base class move it.
		self.lists["tracks_list"].visible("tracks_list" in self.availableWidgets)
		self.lists["tracks_list"].enableSelection(self.selected_widget == "tracks_list")

	def up(self):
		if self.selected_widget == "tracks_list":
			if self["tracks_list"].selectedIndex > 0:
				self["tracks_list"].instance.moveSelection(self["tracks_list"].instance.moveUp)
			else:
				self["tracks_list"].toggleSelection(False)
				self.selected_widget = "f_buttons"
				self["f_buttons"].enableSelection(True)

	def down(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].enableSelection(False)
			self.selected_widget = "tracks_list"
			self["tracks_list"].toggleSelection(True)
		elif self.selected_widget == "tracks_list":
			if self["tracks_list"].selectedIndex < len(self["tracks_list"].data) - 1:
				self["tracks_list"].instance.moveSelection(self["tracks_list"].instance.moveDown)

	def left(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].movePrevious()

	def right(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].moveNext()
