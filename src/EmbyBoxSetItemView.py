from twisted.internet import threads

from .EmbyRestClient import EmbyApiClient
from .EmbyList import EmbyList
from .EmbyMovieItemView import EmbyMovieItemView
from .EmbyItemViewBase import EmbyItemViewBase
from . import _


class EmbyBoxSetItemView(EmbyItemViewBase):
	skin = ["""<screen name="EmbyMovieItemView" position="fill">
					<!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-10" scaleFlags="moveRightTop"/>
					<widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="infoline" position="60,160" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1"/>
					<widget name="plot" position="60,230" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="f_buttons" position="60,440" size="924,65" font="Regular;26" transparent="1"/>
					<widget name="boxset_items" position="40,600" size="e-80,426" iconWidth="232" iconHeight="330" font="Regular;20" scrollbarMode="showNever" iconType="Primary" orientation="orHorizontal" transparent="1"/>
			   </screen>"""]  # noqa: E124

	def __init__(self, session, item, backdrop=None, logo=None):
		EmbyItemViewBase.__init__(self, session, item, backdrop)

		self.availableWidgets = ["f_buttons", "boxset_items"]
		self.selected_widget = "boxset_items"
		self["boxset_items"] = EmbyList()
		self.lists = {}

	def loadItemInUI(self, result):
		self.preLayoutFinished()
		self["f_buttons"].enableSelection(False)
		self["f_buttons"].setItem(self.item)
		self.loadItemDetails(self.item, self.backdrop)
		threads.deferToThread(self.loadBoxSetDetails)

	def processItem(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].getSelectedButton()[3]()
		else:
			self.session.openWithCallback(self.exitCallback, EmbyMovieItemView, self[self.selected_widget].selectedItem, self.backdrop)

	def exitCallback(self, *result):
		if not len(result):
			return
		result = result[0]
		self.exitResult = result
		threads.deferToThread(self.loadBoxSetDetails)

	def up(self):
		if self.selected_widget == "f_buttons":
			return
		else:
			self[self.selected_widget].toggleSelection(False)
			self.selected_widget = "f_buttons"
			self["f_buttons"].enableSelection(True)

	def down(self):
		if self.selected_widget == "boxset_items":
			return
		else:
			self["f_buttons"].enableSelection(False)
			self.selected_widget = "boxset_items"
			self[self.selected_widget].toggleSelection(True)

	def left(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].movePrevious()
		else:
			if hasattr(self[self.selected_widget].instance, "prevItem"):
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.prevItem)
			else:
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveLeft)

	def right(self):
		if self.selected_widget == "f_buttons":
			self["f_buttons"].moveNext()
		else:
			if hasattr(self[self.selected_widget].instance, "nextItem"):
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.nextItem)
			else:
				self[self.selected_widget].instance.moveSelection(self[self.selected_widget].instance.moveRight)

	def loadBoxSetDetails(self):
		items = EmbyApiClient.getBoxsetsChildren(self.item_id)
		list = []
		if items:
			i = 0
			for item in items:
				played_perc = item.get("UserData", {}).get("PlayedPercentage", "0")
				list.append((i, item, item.get('Name'), None, played_perc, True))
				i += 1
			self["boxset_items"].loadData(list)
