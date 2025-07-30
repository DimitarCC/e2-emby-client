# for localized messages
from . import _, PluginLanguageDomain

from sys import modules
from twisted.internet import threads
from enigma import eServiceReference, eTimer
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen, ScreenSummary
from Screens.InfoBar import InfoBar
from Components.ActionMap import ActionMap, HelpableActionMap, NumberActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.SystemInfo import BoxInfo
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyInfoLine import EmbyInfoLine
from .EmbyPlayer import EmbyPlayer
from .EmbySetup import initConfig
from os import path, fsync, rename, makedirs, remove

import threading
import os
import uuid

from PIL import Image

write_lock = threading.Lock()
plugin_dir = path.dirname(modules[__name__].__file__)

initConfig()

from .EmbyRestClient import EmbyApiClient


class E2EmbyHome(Screen):
	skin = ["""<screen name="E2EmbyHome" position="fill">
					<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-220,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="title_logo" position="60,140" size="924,60" alphatest="blend"/>
					<widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="subtitle" position="65,215" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
					<widget name="infoline" position="60,220" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="60,290" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="backdrop" position="e-1062,0" size="1062,600" alphatest="blend"/>
					<widget name="list_header" position="55,570" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left"/>
					<widget name="list_watching_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left"/>
					<widget name="list_recent_movies_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left"/>
					<widget name="list" position="40,610" size="e-80,230" scrollbarMode="showNever" orientation="orHorizontal" transparent="1">
					</widget>
					<widget name="list_watching" position="35,820" size="e-80,270" iconWidth="338" iconHeight="192" scrollbarMode="showNever" iconType="Thumb" orientation="orHorizontal" transparent="1">
					</widget>
					<widget name="list_recent_movies" position="35,1150" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
					<widget name="list_recent_tvshows_header" position="-1920,-1080" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left"/>
					<widget name="list_recent_tvshows" position="35,1600" size="e-80,270" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
				</screen>"""]  # noqa: E124

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Emby"))
		self.selected_widget = "list"
		self.home_loaded = False
		self.availableWidgets = ["list"]

		self.slots_layout = {}
		self.slots_layout[0] = 570
		self.slots_layout[1] = 860
		self.slots_layout[2] = 1240
		self.slots_layout[3] = 1620

		self["title_logo"] = Pixmap()
		self["title"] = Label()
		self["subtitle"] = Label()
		self["infoline"] = EmbyInfoLine(self)
		self["plot"] = Label()
		self["backdrop"] = Pixmap()
		self["list_header"] = Label(_("My Media"))
		self["list"] = EmbyList(True)
		self["list_watching_header"] = Label(_("Continue watching"))
		self["list_watching"] = EmbyList()
		self["list_recent_movies_header"] = Label(_("Recently released movies"))
		self["list_recent_movies"] = EmbyList()
		self["list_recent_tvshows_header"] = Label(_("Recently released tvshows"))
		self["list_recent_tvshows"] = EmbyList()
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText(_("Add provider"))
		self["key_yellow"] = StaticText(_("Generate bouquets"))
		self["key_blue"] = StaticText(_("Clear all data"))
		self["key_info"] = StaticText()
		self["description"] = StaticText(_("Press OK to edit the currently selected provider"))
		self.lists = {}
		self.lists["list"] = EmbyListController(self["list"], self["list_header"])
		self.lists["list_watching"] = EmbyListController(self["list_watching"], self["list_watching_header"])
		self.lists["list_recent_movies"] = EmbyListController(self["list_recent_movies"], self["list_recent_movies_header"])
		self.lists["list_recent_tvshows"] = EmbyListController(self["list_recent_tvshows"], self["list_recent_tvshows_header"])
		self.access_token = None
		self.mbpTimer = eTimer()
		self.processing_cover = False
		self.deferred_cover_url = None
		self.deferred_image_tag = None
		self.last_item_id = None
		self.last_cover = ""
		self.mask_alpha = Image.open(os.path.join(plugin_dir, "mask.png")).split()[3]
		if self.mask_alpha.mode != "L":
			self.mask_alpha = self.mask_alpha.convert("L")
		self.onShown.append(self.__onShown)
		self.onClose.append(self.__onClose)
		self.onLayoutFinish.append(self.__onLayoutFinished)
		self.plot_posy_orig = 290
		self.plot_height_orig = 168
		self.plot_width_orig = 924

		self["actions"] = ActionMap(["E2EmbyActions",],
			{
				"cancel": self.close,  # KEY_RED / KEY_EXIT
				# "save": self.addProvider,  # KEY_GREEN
				"ok": self.processItem,
				# "yellow": self.keyYellow,
				# "blue": self.clearData,
			}, -1)  # noqa: E123

		self["nav_actions"] = ActionMap(["NavigationActions",],
			{
				"up": self.up,
				"down": self.down,
				"left": self.left,
				"right": self.right,
				# "blue": self.clearData,
			}, -2)  # noqa: E123

		# self["infoActions"] = ActionMap(["E2EmbyActions",],
		# 	{
		# 		"info": self.info,
		# 	}, -1)  # noqa: E123

	def __onLayoutFinished(self):
		pass

	def __onShown(self):
		self.lists["list_watching"].enableSelection(self.selected_widget == "list_watching")
		self.lists["list_recent_movies"].enableSelection(self.selected_widget == "list_recent_movies")
		self.lists["list_recent_tvshows"].enableSelection(self.selected_widget == "list_recent_tvshows")
		if not self.home_loaded:
			self.lists["list_watching"].visible(False)
			self.lists["list_recent_movies"].visible(False)
			self.lists["list_recent_tvshows"].visible(False)
			threads.deferToThread(self.loadHome)

	def left(self):
		if hasattr(self[self.selected_widget].instance, "prevItem"):
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.prevItem)
		else:
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveLeft)

		threads.deferToThread(self.loadSelectedItemDetails)

	def right(self):
		if hasattr(self[self.selected_widget].instance, "nextItem"):
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.nextItem)
		else:
			self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveRight)

		threads.deferToThread(self.loadSelectedItemDetails)

	def up(self):
		current_widget_index = self.availableWidgets.index(self.selected_widget)
		if current_widget_index == 0:
			return
		y = self.slots_layout[0]

		prevWidgetName = self.availableWidgets[current_widget_index - 1]
		prevItem = self.lists[prevWidgetName]
		prevItem.move(40, y).visible(True).enableSelection(True)
		y += prevItem.getHeight() + 40
		self.selected_widget = prevWidgetName

		for item in self.availableWidgets[current_widget_index:]:
			self.lists[item].move(40, y).enableSelection(False)
			y += self.lists[item].getHeight() + 40

		threads.deferToThread(self.loadSelectedItemDetails)

	def down(self):
		current_widget_index = self.availableWidgets.index(self.selected_widget)
		if current_widget_index == len(self.availableWidgets) - 1:
			return
		safe_index = min(current_widget_index + 1, len(self.availableWidgets))
		for item in self.availableWidgets[:safe_index]:
			self.lists[item].visible(False).enableSelection(False)

		y = self.slots_layout[0]
		selEnabled = True
		for item in self.availableWidgets[safe_index:]:
			self.lists[item].move(40, y).enableSelection(selEnabled)
			y += self.lists[item].getHeight() + 40
			if selEnabled:
				self.selected_widget = item
			selEnabled = False

		threads.deferToThread(self.loadSelectedItemDetails)

	def processItem(self):
		widget = self[self.selected_widget]
		selected_item = widget.getCurrentItem()
		if widget.isLibrary:
			pass
		else:
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

	def downloadCover(self, item_id, icon_img, selected_item=None):
		url = (item_id, icon_img)
		if self.deferred_cover_url and self.deferred_cover_url == url:
			return
		if self.processing_cover:
			self.deferred_cover_url = url
			self.deferred_image_tag = icon_img
			return
		self.processing_cover = True
		if not self.deferred_cover_url:
			backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1062, height=600, image_type="Backdrop", alpha_channel=self.mask_alpha)
			if backdrop_pix:
				sel_item = self[self.selected_widget].selectedItem
				if not self.deferred_cover_url and sel_item and sel_item[5] and (not self.last_item_id or item_id == self.last_item_id):
					self["backdrop"].setPixmap(backdrop_pix)
				else:
					self.deferred_image_tag = None
					self["backdrop"].setPixmap(None)
				if self.deferred_cover_url:
					item_id, defferred_tag = self.deferred_cover_url
					self.deferred_cover_url = None
					icon_img = self.deferred_image_tag
					self.deferred_image_tag = None
					self.processing_cover = False
					threads.deferToThread(self.downloadCover, item_id, defferred_tag)
				self.processing_cover = False
			else:
				self.processing_cover = False
				self.deferred_cover_url = None
				if selected_item:
					selected_item = (selected_item[0], selected_item[1], selected_item[2], selected_item[3], selected_item[4], False)
				self["backdrop"].setPixmap(None)

	def mdbCover(self, url, icon_img):
		threads.deferToThread(self.downloadCover, url, icon_img)

	def loadSelectedItemDetails(self):
		widget = self[self.selected_widget]
		sel_item = widget.selectedItem
		if not sel_item:
			return

		item = sel_item and sel_item[1] or {}
		item_id = item.get("Id")
		if widget.isLibrary:
			item = EmbyApiClient.getRandomItemFromLibrary(item_id, item.get("CollectionType"))
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
			logo_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=logo_tag, max_height=60, image_type="Logo", format="png")
			if logo_pix:
				self["title_logo"].setPixmap(logo_pix)
				self["title"].text = ""
			else:
				if itemType == "Episode":
					self["title"].text = " ".join(item.get("SeriesName", "").splitlines())
				else:
					self["title"].text = " ".join(item.get("Name", "").splitlines())
				self["title_logo"].setPixmap(None)
		else:
			if itemType == "Episode":
				self["title"].text = " ".join(item.get("SeriesName", "").splitlines())
			else:
				self["title"].text = " ".join(item.get("Name", "").splitlines())
			self["title_logo"].setPixmap(None)

		if itemType == "Episode":
			sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
			self["subtitle"].text = sub_title
			subtitlesize = self["subtitle"].getSize()
			plotpos = self["plot"].instance.position()
			self["plot"].move(plotpos.x(), self.plot_posy_orig + subtitlesize[1])
			self["plot"].resize(self.plot_width_orig, self.plot_height_orig - subtitlesize[1] - 20)
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
			self["infoline"].move(infolinepos.x(), self.plot_posy_orig - infolinesize[1] - 10)

		self["infoline"].updateInfo(item)

		self["plot"].text = item.get("Overview", "")

		self.last_item_id = item_id

		backdrop_image_tags = item.get("BackdropImageTags")
		parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
		if parent_backdrop_image_tags:
			backdrop_image_tags = parent_backdrop_image_tags

		if not backdrop_image_tags or len(backdrop_image_tags) == 0:
			self["backdrop"].setPixmap(None)
			return

		icon_img = backdrop_image_tags[0]
		parent_b_item_id = item.get("ParentBackdropItemId")
		if parent_b_item_id:
			item_id = parent_b_item_id
			self.last_item_id = item_id

		self.downloadCover(item_id, icon_img, sel_item)

	def loadHome(self):
		# for now hardcode username and password here
		EmbyApiClient.authorizeUser("dimitarcc", "Japanese1")

		libs = EmbyApiClient.getLibraries()
		libs_list = []
		movie_libs_ids = []
		tvshow_libs_ids = []
		music_libs_ids = []
		i = 0
		if libs:
			for lib in libs:
				colType = lib.get("CollectionType")
				if colType and colType == "movies":
					movie_libs_ids.append(int(lib.get("Id")))

				if colType and colType == "tvshows":
					tvshow_libs_ids.append(int(lib.get("Id")))

				if colType and colType == "music":
					music_libs_ids.append(int(lib.get("Id")))

				libs_list.append((i, lib, lib.get('Name'), None, "0", True))
				i += 1
			self["list"].loadData(libs_list)

		if self.loadEmbyList(self["list_watching"], "Resume"):
			if "list_watching" not in self.availableWidgets:
				self.availableWidgets.append("list_watching")
		if movie_libs_ids:
			if self.loadEmbyList(self["list_recent_movies"], "LastMovies", movie_libs_ids):
				if "list_recent_movies" not in self.availableWidgets:
					self.availableWidgets.append("list_recent_movies")
		if tvshow_libs_ids:
			if self.loadEmbyList(self["list_recent_tvshows"], "LastSeries", tvshow_libs_ids):
				if "list_recent_tvshows" not in self.availableWidgets:
					self.availableWidgets.append("list_recent_tvshows")

		try:
			slot = 0
			self.lists["list"].move(40, self.slots_layout[slot]).visible(True)
			slot += 1
			if "list_watching" in self.availableWidgets:
				self.lists["list_watching"].move(40, self.slots_layout[slot]).visible(True).enableSelection(self.selected_widget == "list_watching")
				slot += 1
			if "list_recent_movies" in self.availableWidgets:
				self.lists["list_recent_movies"].move(40, self.slots_layout[slot]).visible(True).enableSelection(self.selected_widget == "list_recent_movies")
				slot += 1
			if "list_recent_tvshows" in self.availableWidgets:
				self.lists["list_recent_tvshows"].move(40, self.slots_layout[slot]).visible(True).enableSelection(self.selected_widget == "list_recent_tvshows")
				slot += 1
			self.loadSelectedItemDetails()
		except:
			pass

		self.home_loaded = True

	def __onClose(self):
		pass

	def loadEmbyList(self, widget, type, parent_ids=[]):
		items = []
		type_part = ""
		parent_part = ""
		sortBy = "DatePlayed"
		includeItems = "Movie"
		if type == "Resume":
			type_part = "/Resume"
			sortBy = "DatePlayed"
			includeItems = "Episode,Movie"
		elif type == "LastMovies":
			sortBy = "DateCreated"
			includeItems = "Movie&IsMovie=true&Recursive=true&Filters=IsNotFolder"
		elif type == "LastSeries":
			sortBy = "DateCreated"
			includeItems = "Series&IsFolder=true&Recursive=true"
		if not parent_ids:
			items.extend(EmbyApiClient.getItems(type_part, sortBy, includeItems, parent_part))
		else:
			for parent_id in parent_ids:
				parent_part = f"&ParentId={parent_id}"
				part_items = EmbyApiClient.getItems(type_part, sortBy, includeItems, parent_part)
				items.extend(part_items)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			widget.loadData(list)
		return len(list) > 0


def main(session, **kwargs):
	session.open(E2EmbyHome)


def startHome(menuid):
	if menuid != "mainmenu":
		return []
	return [(_("E2-Emby"), main, "e2_emby_menu", 100)]


def sessionstart(reason, session, **kwargs):
	makedirs("/tmp/emby/", exist_ok=True)


def Plugins(path, **kwargs):
	try:
		result = [
			PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart, needsRestart=False),
			PluginDescriptor(name=_("E2-Emby"), description=_("A client for Emby server"), where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=startHome),
			PluginDescriptor(name=_("E2-Emby Client"), description=_("A client for Emby server"), where=PluginDescriptor.WHERE_PLUGINMENU, icon='plugin.png', fnc=main)
		]
		return result
	except ImportError:
		return PluginDescriptor()
