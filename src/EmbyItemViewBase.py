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

EXIT_RESULT_MOVIE = 1
EXIT_RESULT_SERIES = 2
EXIT_RESULT_BOXSET = 3
EXIT_RESULT_EPISODE = 4
EXIT_RESULT_SEASON = 5


class EmbyItemViewBase(Screen):
    def __init__(self, session, item, backdrop=None):
        Screen.__init__(self, session)
        self.setTitle(_("Emby") + item.get("Name"))
        self.exitResult = None
        self.init_loaded = False
        self.backdrop = backdrop
        self.item_id = item.get("Id")
        self.item = item
        self.onShown.append(self.__onShown)
        self.onLayoutFinish.append(self.__onLayoutFinished)
        self.top_widget_pos_y = 0

        self.mask_alpha = Image.open(os.path.join(plugin_dir, "mask_l.png")).split()[3]
        if self.mask_alpha.mode != "L":
            self.mask_alpha = self.mask_alpha.convert("L")

        self.availableWidgets = ["f_buttons"]
        self.selected_widget = "f_buttons"
        self["title_logo"] = Pixmap()
        self["title"] = Label()
        self["infoline"] = EmbyInfoLine(self)
        self["plot"] = Label()
        self["backdrop"] = Pixmap()
        self["f_buttons"] = EmbyItemFunctionButtons(self)
        self["f_buttons"].onPlayerExit.append(self.__onPlayerClosed)
        self.lists = {}
        self["actions"] = ActionMap(["E2EmbyActions",],
            {
                "cancel": self.__closeScreen,  # KEY_RED / KEY_EXIT
                # "save": self.addProvider,  # KEY_GREEN
                "ok": self.processItem,
                # "yellow": self.keyYellow,
                # "blue": self.clearData,
            }, -1)
        self["nav_actions"] = ActionMap(["NavigationActions",],
            {
                "up": self.up,
                "down": self.down,
                "left": self.left,
                "right": self.right,
                # "blue": self.clearData,
            }, -2)

    def __closeScreen(self):
        self.close(self.exitResult)

    def onPlayerClosedResult(self):
        pass

    def __onPlayerClosed(self):
        self.onPlayerClosedResult()
        self.loadItemInfoFromServer(self.item_id)
        self["infoline"].updateInfo(self.item)
        self["f_buttons"].setItem(self.item)

    def preLayoutFinished(self):
        pass

    def __onLayoutFinished(self):
        if not self.init_loaded:
            keys = list(self.lists.keys())
            top_widget = keys[0] if len(keys) > 1 else self.availableWidgets[0]
            if top_widget != "f_buttons":
                self.top_widget_pos_y = self.lists[top_widget].getTopLeftCornerPos()[1]
            else:
                self.top_widget_pos_y = self[top_widget].instance.position().y()
            load_res = self.loadItemInfoFromServer(self.item_id)
            self.preLayoutFinished()
            self.loadItemInUI(load_res)
            self.init_loaded = True

    def loadItemInUI(self, result):
        self["f_buttons"].setItem(self.item)
        self.loadItemDetails(self.item, self.backdrop)

    def __onShown(self):
        pass

    def processItem(self):
        if self.selected_widget == "f_buttons":
            self["f_buttons"].getSelectedButton()[3]()

    def up(self):
        keys = list(self.lists.keys())
        keys = [key for key in keys if key in self.availableWidgets]
        if self.selected_widget != "f_buttons":
            current_widget_index = keys.index(self.selected_widget)
            if current_widget_index == 0:
                self.lists[self.selected_widget].enableSelection(False)
                self.selected_widget = "f_buttons"
                self["f_buttons"].enableSelection(True)
                return

            y = self.top_widget_pos_y

            prevWidgetName = keys[current_widget_index - 1]
            prevItem = self.lists[prevWidgetName]
            prevItem.move(40, y).visible(True).enableSelection(True)
            y += prevItem.getHeight() + 40
            self.selected_widget = prevWidgetName

            for item in keys[current_widget_index:]:
                self.lists[item].move(40, y).enableSelection(False)
                y += self.lists[item].getHeight() + 40

    def down(self):
        keys = list(self.lists.keys())
        keys = [key for key in keys if key in self.availableWidgets]
        if self.selected_widget != "f_buttons":
            current_widget_index = keys.index(self.selected_widget)
            if current_widget_index == len(keys) - 1:
                return
            safe_index = min(current_widget_index + 1, len(keys))
            for item in keys[:safe_index]:
                self.lists[item].visible(False).enableSelection(False)

            y = self.top_widget_pos_y
            selEnabled = True
            for item in keys[safe_index:]:
                self.lists[item].move(40, y).enableSelection(selEnabled)
                y += self.lists[item].getHeight() + 40
                if selEnabled:
                    self.selected_widget = item
                selEnabled = False
        else:
           self.selected_widget = keys[0]
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

    def infoRetrieveInject(self, item):
        pass

    def loadItemInfoFromServer(self, item_id):
        self.item = EmbyApiClient.getSingleItem(item_id=item_id)
        return True

    def injectAfterLoad(self, item):
        pass

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
            backdrop_image_tags = item.get("BackdropImageTags", [])
            parent_backdrop_image_tags = item.get("ParentBackdropImageTags", [])
            if parent_backdrop_image_tags:
                backdrop_image_tags = parent_backdrop_image_tags

            if not backdrop_image_tags or len(backdrop_image_tags) == 0:
                self["backdrop"].setPixmap(None)
            else:
                icon_img = backdrop_image_tags[0]
                parent_b_item_id = item.get("ParentBackdropItemId")
                if parent_b_item_id:
                    item_id = parent_b_item_id

                threads.deferToThread(self.downloadCover, item_id, icon_img)

        self.injectAfterLoad(item)

    def downloadCover(self, item_id, icon_img):
        backdrop_pix = EmbyApiClient.getItemImage(item_id=item_id, logo_tag=icon_img, width=1280, image_type="Backdrop", alpha_channel=self.mask_alpha)
        if backdrop_pix:
            self["backdrop"].setPixmap(backdrop_pix)
        else:
            self["backdrop"].setPixmap(None)
