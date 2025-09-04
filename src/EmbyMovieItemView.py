from twisted.internet import threads

from Components.Label import Label

from .EmbyItemView import EmbyItemView
from .EmbyItemViewBase import EXIT_RESULT_MOVIE
from .EmbyListController import EmbyListController
from .EmbyList import EmbyList
from .EmbyRestClient import EmbyApiClient
from . import _


class EmbyMovieItemView(EmbyItemView):
	skin = ["""<screen name="EmbyMovieItemView" position="fill">
					<!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-10" scaleFlags="moveRightTop"/>
					<widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="infoline" position="60,160" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1"/>
					<widget name="tagline" position="60,230" size="1400,50" alphatest="blend" font="Bold;42" foregroundColor="yellowsoft" transparent="1" shadowColor="black" shadowOffset="-1,-1"/>
					<widget name="plot" position="60,230" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="f_buttons" position="60,480" size="924,65" font="Regular;26" transparent="1"/>
					<widget name="cast_header" position="40,590" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_cast" position="40,660" size="e-80,426" iconWidth="205" iconHeight="310" font="Regular;19" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="chapters_header" position="40,1126" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_chapters" position="40,1190" size="e-80,310" iconWidth="395" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" transparent="1"/>
					<widget name="header_extras" position="40,1520" size="1100,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_extras" position="40,1580" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="header_parent_boxsets" position="40,2046" size="1100,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_parent_boxsets" position="40,2106" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="header_similar" position="40,2572" size="1100,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_similar" position="40,2632" size="e-80,426" iconWidth="232" iconHeight="330" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
			</screen>"""]

	def __init__(self, session, item, backdrop=None, logo=None):
		EmbyItemView.__init__(self, session, item, backdrop, logo)
		self.setTitle(_("Emby") + item.get("Name"))

		self["tagline"] = Label()
		self["header_parent_boxsets"] = Label(_("Included in Collections"))
		self["list_parent_boxsets"] = EmbyList()
		self.lists["list_parent_boxsets"] = EmbyListController(self["list_parent_boxsets"], self["header_parent_boxsets"])
		self["header_similar"] = Label(_("Similar"))
		self["list_similar"] = EmbyList()
		self.lists["list_similar"] = EmbyListController(self["list_similar"], self["header_similar"])

	def preLayoutFinished(self):
		plot_pos = self["plot"].instance.position()
		tagline_h = self["tagline"].instance.size().height()
		taglines = self.item.get("Taglines", [])
		if len(taglines) > 0:
			self["plot"].move(plot_pos.x(), plot_pos.y() + tagline_h + 15)
		EmbyItemView.preLayoutFinished(self)

	def processItem(self):
		EmbyItemView.processItem(self)
		if self.selected_widget == "list_parent_boxsets":
			selected_item = self[self.selected_widget].selectedItem
			from .EmbyBoxSetItemView import EmbyBoxSetItemView
			self.session.openWithCallback(self.exitCallback, EmbyBoxSetItemView, selected_item)
		elif self.selected_widget == "list_similar":
			selected_item = self[self.selected_widget].selectedItem
			from .EmbyMovieItemView import EmbyMovieItemView as MovieView
			self.session.openWithCallback(self.exitCallback, MovieView, selected_item)

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		self.exitResult = result

	def loadExtraItems(self, itemObj):
		item_id = itemObj.get("Id")
		extras = EmbyApiClient.getExtrasForItem(item_id)
		list = []
		if extras:
			i = 0
			for item in extras:
				list.append((i, item, item.get('Name'), None, "0", True))
				i += 1
			self["list_extras"].loadData(list)
		if len(list) > 0:
			self.availableWidgets.append("list_extras")
			self.lists["list_extras"].visible(True)
		else:
			self.lists["list_extras"].visible(False)

		boxsets = EmbyApiClient.getBoxsetsForItem(item_id)
		list = []
		if boxsets:
			i = 0
			for item in boxsets:
				list.append((i, item, item.get('Name'), None, "0", True))
				i += 1
			self["list_parent_boxsets"].loadData(list)
		if len(list) > 0:
			self.availableWidgets.append("list_parent_boxsets")
			self.lists["list_parent_boxsets"].visible(True)
		else:
			self.lists["list_parent_boxsets"].visible(False)

		similar = EmbyApiClient.getSimilarForItem(item_id)
		list = []
		if similar:
			i = 0
			for item in similar:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["list_similar"].loadData(list)
		if len(list) > 0:
			self.availableWidgets.append("list_similar")
			self.lists["list_similar"].visible(True)
		else:
			self.lists["list_similar"].visible(False)

	def injectAfterLoad(self, item):
		EmbyItemView.injectAfterLoad(self, item)
		threads.deferToThread(self.loadExtraItems, item)

	def onPlayerClosedResult(self):
		self.exitResult = EXIT_RESULT_MOVIE

	def infoRetrieveInject(self, item):
		taglines = item.get("Taglines", [])
		if len(taglines) > 0:
			tagline = taglines[0]
			self["tagline"].text = tagline
