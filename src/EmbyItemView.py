from . import _

import os
from sys import modules
from twisted.internet import threads
from Screens.Screen import Screen, ScreenSummary
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap

from .EmbyRestClient import EmbyApiClient
from .EmbyInfoLine import EmbyInfoLine

from PIL import Image

plugin_dir = os.path.dirname(modules[__name__].__file__)

class EmbyItemView(Screen):
    # skin = ["""<screen name="EmbyItemView" position="fill">
    #                 <ePixmap position="60,30" size="198,60" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/E2EmbyClient/emby-verysmall.png" alphatest="blend"/>
    #                 <widget backgroundColor="background" font="Bold; 50" alphatest="blend" foregroundColor="white" halign="right" position="e-275,25" render="Label" size="220,60" source="global.CurrentTime" valign="center" zPosition="20" cornerRadius="20" transparent="1"  shadowColor="black" shadowOffset="-1,-1">
    #                     <convert type="ClockToText">Default</convert>
    #                 </widget>
    #                 <widget name="backdrop" position="e-1280,0" size="1280,720" alphatest="blend" zPosition="-3"/>
    #                 <widget name="title_logo" position="60,140" size="924,80" alphatest="blend"/>
    #                 <widget name="title" position="60,130" size="924,80" alphatest="blend" font="Bold;70" transparent="1" noWrap="1"/>
    #                 <widget name="subtitle" position="65,235" size="924,40" alphatest="blend" font="Bold;35" transparent="1"/>
    #                 <widget name="infoline" position="60,240" size="1200,60" font="Bold;32" fontAdditional="Bold;28" transparent="1" />
    #                 <widget name="plot" position="60,310" size="924,168" alphatest="blend" font="Regular;30" transparent="1"/>
    #             </screen>"""]  # noqa: E124

    def __init__(self, session, item, backdrop=None):
        Screen.__init__(self, session)
        self.setTitle(_("Emby") + item.get("Name"))
        self.backdrop = backdrop
        self.item_id = item.get("Id")
        self.item = item
        self.onShown.append(self.__onShown)
        self.onLayoutFinish.append(self.__onLayoutFinished)

        self.mask_alpha = Image.open(os.path.join(plugin_dir, "mask_l.png")).split()[3]
        if self.mask_alpha.mode != "L":
            self.mask_alpha = self.mask_alpha.convert("L")

        self.plot_posy_orig = 310
        self.plot_height_orig = 168
        self.plot_width_orig = 924

        self["title_logo"] = Pixmap()
        self["title"] = Label()
        self["subtitle"] = Label()
        self["infoline"] = EmbyInfoLine(self)
        self["plot"] = Label()
        self["backdrop"] = Pixmap()
        self["actions"] = ActionMap(["E2EmbyActions",],
            {
                "cancel": self.close,  # KEY_RED / KEY_EXIT
                # "save": self.addProvider,  # KEY_GREEN
                #"ok": self.processItem,
                # "yellow": self.keyYellow,
                # "blue": self.clearData,
            }, -1)  # noqa: E123
        

    def preLayoutFinished(self):
        pass

    def __onLayoutFinished(self):
        self.item = self.loadItemInfoFromServer(self.item_id)
        self.loadSelectedItemDetails(self.item, self.backdrop)
        # threads.deferToThread(self.loadItemInfoFromServer, self.item_id).addCallback(self.loadItemDetailsInUI)

    def __onShown(self):
        pass

    def loadItemDetailsInUI(self, item):
        self.item = item
        self.loadSelectedItemDetails(self.item, self.backdrop)

    def infoRetrieveInject(self, item):
        pass

    def loadItemInfoFromServer(self, item_id):
        return EmbyApiClient.getSingleItem(item_id=item_id)


    def loadSelectedItemDetails(self, item, backdrop_pix):
        self.preLayoutFinished()
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
            logo_widget_size = self["title_logo"].instance.size()
            max_w = logo_widget_size.width()
            max_h = logo_widget_size.height()
            logo_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=logo_tag, max_width=max_w, max_height=max_h, image_type="Logo", format="png")
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

        self["infoline"].updateInfo(item)

        self.infoRetrieveInject(item=item)

        self["plot"].text = item.get("Overview", "")

        if backdrop_pix:
            self["backdrop"].setPixmap(backdrop_pix)
        else:
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

            threads.deferToThread(self.downloadCover, item_id, icon_img)


    def downloadCover(self, item_id, icon_img):
        backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1280, image_type="Backdrop", alpha_channel=self.mask_alpha)
        if backdrop_pix:
            self["backdrop"].setPixmap(backdrop_pix)
        else:
            self["backdrop"].setPixmap(None)

        