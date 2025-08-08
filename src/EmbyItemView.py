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
from .EmbyItemFunctionButtons import EmbyItemFunctionButtons
from .EmbyList import EmbyList
from .EmbyListController import EmbyListController

from PIL import Image

plugin_dir = os.path.dirname(modules[__name__].__file__)

class EmbyItemView(Screen):
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

        self.availableWidgets = ["f_buttons"]
        self.selected_widget = "f_buttons"
        self["title_logo"] = Pixmap()
        self["title"] = Label()
        self["subtitle"] = Label()
        self["infoline"] = EmbyInfoLine(self)
        self["plot"] = Label()
        self["backdrop"] = Pixmap()
        self["f_buttons"] = EmbyItemFunctionButtons(self)
        self["cast_header"] = Label(_("Cast/Crew"))
        self["list_cast"] = EmbyList(type="cast")
        self.cast_controller = EmbyListController(self["list_cast"], self["cast_header"])
        self.lists = {}
        self.lists["list_cast"] = self.cast_controller
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

        

    def preLayoutFinished(self):
        pass

    def __onLayoutFinished(self):
        self.item = self.loadItemInfoFromServer(self.item_id)
        self.preLayoutFinished()
        self["f_buttons"].setItem(self.item)
        cast_header_y = self["cast_header"].instance.position().y()
        self.cast_controller.move(40, cast_header_y).visible(True).enableSelection(False)
        self.availableWidgets.append("list_cast")
        self.loadItemDetails(self.item, self.backdrop)
        # threads.deferToThread(self.loadItemInfoFromServer, self.item_id).addCallback(self.loadItemDetailsInUI)

    def __onShown(self):
        pass

    def processItem(self):
        if self.selected_widget == "f_buttons":
            self["f_buttons"].getSelectedButton()[3]()

    def up(self):
        current_widget_index = self.availableWidgets.index(self.selected_widget)
        if current_widget_index == 0:
            return
        
        if current_widget_index > 1:
            y = 560

            prevWidgetName = self.availableWidgets[current_widget_index - 1]
            prevItem = self.lists[prevWidgetName]
            prevItem.move(40, y).visible(True).enableSelection(True)
            y += prevItem.getHeight() + 40
            self.selected_widget = prevWidgetName

            for item in self.availableWidgets[current_widget_index:]:
                self.lists[item].move(40, y).enableSelection(False)
                y += self.lists[item].getHeight() + 40
        else:
           self.lists[self.selected_widget].enableSelection(False)
           self.selected_widget = "f_buttons"
           self["f_buttons"].enableSelection(True) 

    def down(self):
        current_widget_index = self.availableWidgets.index(self.selected_widget)
        if current_widget_index == len(self.availableWidgets) - 1:
            return
        safe_index = min(current_widget_index + 1, len(self.availableWidgets))
        for item in self.availableWidgets[1:safe_index]:
            self.lists[item].visible(False).enableSelection(False)

        if self.selected_widget != "f_buttons":
            y = 560
            selEnabled = True
            for item in self.availableWidgets[safe_index:]:
                self.lists[item].move(40, y).enableSelection(selEnabled)
                y += self.lists[item].getHeight() + 40
                if selEnabled:
                    self.selected_widget = item
                selEnabled = False
        else:
           self.selected_widget = self.availableWidgets[safe_index]
           self.lists[self.selected_widget].enableSelection(True)
           self["f_buttons"].enableSelection(False)

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

    def loadItemDetailsInUI(self, item):
        self.item = item
        self.loadItemDetails(self.item, self.backdrop)

    def infoRetrieveInject(self, item):
        pass

    def loadItemInfoFromServer(self, item_id):
        return EmbyApiClient.getSingleItem(item_id=item_id)


    def loadItemDetails(self, item, backdrop_pix):
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

        cast_crew_list = item.get("People", [])
        list = []
        if cast_crew_list:
            i = 0
            for item in cast_crew_list:
                list.append((i, item, f"{item.get('Name')}\n({item.get("Role", item.get("Type"))})", None, "0", True))
                i += 1
            self["list_cast"].loadData(list)


    def downloadCover(self, item_id, icon_img):
        backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1280, image_type="Backdrop", alpha_channel=self.mask_alpha)
        if backdrop_pix:
            self["backdrop"].setPixmap(backdrop_pix)
        else:
            self["backdrop"].setPixmap(None)

        