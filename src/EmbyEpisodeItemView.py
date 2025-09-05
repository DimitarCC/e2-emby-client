from Components.Label import Label

from .EmbyItemView import EmbyItemView
from .EmbyItemViewBase import EXIT_RESULT_EPISODE
from . import _


class EmbyEpisodeItemView(EmbyItemView):
	skin = ["""<screen name="EmbyEpisodeItemView" position="fill">
					<!--<ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>-->
					<widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
						<convert type="ClockToText">Default</convert>
					</widget>
					<widget name="backdrop" position="0,0" size="e,e" alphatest="blend" zPosition="-3" scaleFlags="moveRightTop"/>
					<widget name="title_logo" position="60,60" size="924,80" alphatest="blend"/>
					<widget name="title" position="60,50" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
					<widget name="subtitle" position="60,170" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
					<widget name="infoline" position="60,230" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
					<widget name="plot" position="60,310" size="924,105" alphatest="blend" font="Regular;30" transparent="1"/>
					<widget name="f_buttons" position="60,480" size="924,70" font="Regular;32" transparent="1"/>
					<widget name="cast_header" position="40,590" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_cast" position="40,660" size="e-80,426" iconWidth="205" iconHeight="310" font="Regular;19" scrollbarMode="showNever" iconType="Primary" transparent="1"/>
					<widget name="chapters_header" position="40,1126" size="900,40" alphatest="blend" font="Regular;28" valign="center" halign="left" transparent="1"/>
					<widget name="list_chapters" position="40,1190" size="e-80,310" iconWidth="395" iconHeight="220" font="Regular;22" scrollbarMode="showNever" iconType="Chapter" transparent="1"/>
				</screen>"""]

	def __init__(self, session, item, backdrop=None, logo=None):
		EmbyItemView.__init__(self, session, item, backdrop, logo)
		self.setTitle(_("Emby") + item.get("Name"))

		self["subtitle"] = Label()
		# self["actions"] = ActionMap(["E2EmbyActions",],
		#     {
		#         "cancel": self.close,  # KEY_RED / KEY_EXIT
		#         # "save": self.addProvider,  # KEY_GREEN
		#         "ok": self.processItem,
		#         # "yellow": self.keyYellow,
		#         # "blue": self.clearData,
		#     }, -1)

	def onPlayerClosedResult(self):
		self.exitResult = EXIT_RESULT_EPISODE

	def infoRetrieveInject(self, item):
		sub_title = f"S{item.get("ParentIndexNumber", 0)}:E{item.get("IndexNumber", 0)} - {" ".join(item.get("Name", "").splitlines())}"
		self["subtitle"].text = sub_title
