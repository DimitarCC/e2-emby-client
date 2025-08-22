from twisted.internet import threads
from twisted.internet.defer import inlineCallbacks, returnValue
from uuid import uuid4

from enigma import eListbox, eListboxPythonMultiContent, eRect, BT_HALIGN_CENTER, BT_VALIGN_CENTER, gFont, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_BLEND, RT_WRAP
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryPixmapAlphaBlend, MultiContentEntryText, MultiContentEntryProgress, MultiContentEntryRectangle
from Components.config import config
from Tools.LoadPixmap import LoadPixmap

from .EmbyRestClient import EmbyApiClient, DIRECTORY_PARSER
from .HelperFunctions import embyDateToString, convert_ticks_to_time, find_index, create_thumb_cache_dir, delete_thumb_cache_dir
from .Variables import plugin_dir, EMBY_THUMB_CACHE_DIR
from . import _, PluginLanguageDomain


class EmbyList(GUIComponent):
    def __init__(self, type="item", isLibrary=False):
        GUIComponent.__init__(self)
        self.widget_id = uuid4()
        self.type = type
        self.isLibrary = isLibrary
        self.onSelectionChanged = []
        self.data = []
        self.itemsForThumbs = []
        self.thumbs = {}
        self.check24 = LoadPixmap("%s/check_24.png" % plugin_dir)
        self.selectionEnabled = True
        self.font = gFont("Regular", 18)
        self.badgeFont = gFont("Regular", 18)
        self.selectedIndex = 0
        self.lastSelectedItemId = None
        self.l = eListboxPythonMultiContent()  # noqa: E741
        self.l.setBuildFunc(self.buildEntry)
        self.spacing_sides = 15
        self.orientations = {"orHorizontal": eListbox.orHorizontal,
                             "orVertical": eListbox.orVertical}
        self.orientation = eListbox.orHorizontal
        self.iconWidth = 270
        self.iconHeight = 152
        self.itemWidth = self.iconWidth + self.spacing_sides * 2
        self.itemHeight = self.iconHeight + 72
        self.l.setItemHeight(self.itemHeight)
        self.l.setItemWidth(self.itemWidth)
        self.icon_type = "Primary"
        self.refreshing = False
        self.running = False
        self.updatingIndexesInProgress = []
        self.interupt = False
        self.items_per_page = 0
        self.currentPage = 0

    GUI_WIDGET = eListbox

    def postWidgetCreate(self, instance):
        create_thumb_cache_dir(self.widget_id)
        instance.setContent(self.l)
        instance.selectionChanged.get().append(self.selectionChanged)
        self.l.setSelectionClip(eRect(0, 0, 0, 0), False)
        threads.deferToThread(self.runQueueProcess)

    def preWidgetRemove(self, instance):
        instance.selectionChanged.get().remove(self.selectionChanged)
        self.interupt = True
        delete_thumb_cache_dir(self.widget_id)

    def selectionChanged(self):
        if isinstance(self.selectedItem, tuple):
            return
        self.selectedIndex = self.l.getCurrentSelectionIndex()
        new_page = self.selectedIndex // self.items_per_page
        if new_page != self.currentPage:
            self.currentPage = new_page
        self.lastSelectedItemId = self.selectedItem.get("Id")
        for x in self.onSelectionChanged:
            x(self, self.selectedItem and self.selectedItem.get("Id"))

    def getCurrentObjectSelection(self):
        return self.l.getCurrentSelection()

    def getCurrentItem(self):
        cur = self.l.getCurrentSelection()
        return cur and cur[1] or {}

    def getCurrentIndex(self):
        return self.instance.getCurrentIndex() or -1

    selectedItem = property(getCurrentItem)

    selectedWidgetItem = property(getCurrentObjectSelection)

    def applySkin(self, desktop, parent):
        attribs = []
        for (attrib, value) in self.skinAttributes[:]:
            if attrib == "orientation":
                self.orientation = self.orientations.get(
                    value, self.orientations["orHorizontal"])
            elif attrib == "font":
                self.font = parseFont(value, parent.scale)
            elif attrib == "badgeFont":
                self.badgeFont = parseFont(value, parent.scale)
            elif attrib == "foregroundColor":
                self.foreColor = parseColor(value).argb()
            elif attrib == "iconType":
                self.icon_type = value
            elif attrib == "iconWidth":
                self.iconWidth = int(value)
            elif attrib == "iconHeight":
                self.iconHeight = int(value)
            else:
                attribs.append((attrib, value))
        self.skinAttributes = attribs
        self.l.setFont(0, self.font)
        self.l.setFont(1, self.badgeFont)
        self.itemWidth = self.iconWidth + self.spacing_sides * 2

        self.l.setItemHeight(self.itemHeight)
        self.l.setItemWidth(self.itemWidth)
        self.instance.setOrientation(self.orientation)
        self.l.setOrientation(self.orientation)
        res = GUIComponent.applySkin(self, desktop, parent)
        self.itemHeight = self.instance.size().height()
        self.items_per_page = self.instance.size().width() // self.itemWidth
        return res

    def toggleSelection(self, enabled):
        self.selectionEnabled = enabled
        self.instance.setSelectionEnable(enabled)

    def loadData(self, items):
        new_index = -1
        if self.lastSelectedItemId:
            new_index = find_index(items, lambda x: x[1].get(
                "Id") == self.lastSelectedItemId)

        self.data = items
        if config.plugins.e2embyclient.thumbcache_loc.value != "/tmp":
            for itm in items:
                item = itm[1]
                if self.type == "item":
                    icon_img = item.get("ImageTags").get("Primary")
                    item_id = item.get("Id")
                    parent_id = item.get("ParentThumbItemId")
                    parent_icon_img = item.get("ParentThumbImageTag")
                    if parent_id and parent_icon_img:
                        item_id = parent_id
                        icon_img = parent_icon_img
                    f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{icon_img}__{self.iconWidth}_{self.iconHeight}.jpg"
                elif self.type == "episodes":
                    icon_img = item.get("ImageTags").get("Primary")
                    item_id = item.get("Id")
                    f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{icon_img}__{self.iconWidth}_{self.iconHeight}.jpg"
                elif self.type == "chapters":
                    item_id = item.get("Id")
                    icon_img = item.get("ImageTag")
                    image_index = item.get("ChapterIndex", -1)
                    f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{icon_img}_{image_index}__{self.iconWidth}_{self.iconHeight}.jpg"
                else:
                    icon_img = item.get("PrimaryImageTag")
                    item_id = item.get("Id")
                    f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{icon_img}.jpg"

                if f_name in DIRECTORY_PARSER.THUMBS:
                    self.thumbs[item_id] = f_name
                else:
                    if self.type != "chapters":
                        backdrop_image_tags = item.get("BackdropImageTags")
                        parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
                        if parent_backdrop_image_tags:
                            backdrop_image_tags = parent_backdrop_image_tags

                        if not backdrop_image_tags or len(backdrop_image_tags) == 0:
                            continue

                        icon_img = backdrop_image_tags[0]
                        parent_b_item_id = item.get("ParentBackdropItemId")
                        if parent_b_item_id:
                            item_id = parent_b_item_id

                        f_name = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{icon_img}__{self.iconWidth}_{self.iconHeight}.jpg"
                        if f_name in DIRECTORY_PARSER.THUMBS:
                            self.thumbs[item_id] = f_name

        self.l.setList(items)
        if new_index > -1:
            self.instance.moveSelectionTo(new_index)

    def get_page_item_ids(self, page_index):
        start = page_index * self.items_per_page
        end = min(start + self.items_per_page, len(self.data))
        return [(item[0], item[1]) for item in self.data[start:end]]

    @inlineCallbacks
    def runQueueProcess(self):
        self.running = True
        while len(self.itemsForThumbs) > 0:
            if self.interupt:
                self.interupt = False
                break
            item_popped = self.itemsForThumbs.pop(0)
            item_index = item_popped[0]
            item = item_popped[1]
            if self.type == "item":
                icon_img = item.get("ImageTags").get("Primary")
                item_id = item.get("Id")
                parent_id = item.get("ParentThumbItemId")
                parent_icon_img = item.get("ParentThumbImageTag")
                if parent_id and parent_icon_img:
                    item_id = parent_id
                    icon_img = parent_icon_img
                    self.icon_type = "Thumb"

                yield self.updateThumbnail(item_id, item_index, item, icon_img)
            elif self.type == "episodes":
                icon_img = item.get("ImageTags").get("Primary")
                item_id = item.get("Id")
                yield self.updateThumbnail(item_id, item_index, item, icon_img)
            elif self.type == "chapters":
                item_id = item.get("Id").split("_")[0]
                icon_img = item.get("ImageTag")
                yield self.updateThumbnail(item_id, item_index, item, icon_img)
            else:
                icon_img = item.get("PrimaryImageTag")
                item_id = item.get("Id")
                person_name = item.get("Name")
                yield self.updateCastThumbnail(item_id, person_name, item_index, icon_img)

        self.running = False

    @inlineCallbacks
    def updateCastThumbnail(self, item_id, person_name, item_index, icon_img):
        icon_pix = None

        if item_index not in self.updatingIndexesInProgress:
            self.updatingIndexesInProgress.append(item_index)

        icon_pix = yield EmbyApiClient.getPersonImageAsync(widget_id=self.widget_id, person_name=person_name, logo_tag=icon_img,
                                                           height=self.iconHeight, req_width=self.iconWidth, req_height=self.iconHeight)
        if not hasattr(self, "data"):
            returnValue(False)
        if item_id not in self.thumbs:
            self.thumbs[item_id] = icon_pix or True

        if item_index in self.updatingIndexesInProgress:
            self.updatingIndexesInProgress.remove(item_index)

        if icon_pix:
            DIRECTORY_PARSER.addToSet(icon_pix)
            self.instance.redrawItemByIndex(item_index)
        returnValue(True)

    @inlineCallbacks
    def updateThumbnail(self, item_id, item_index, item, icon_img):
        icon_pix = None
        orig_item_id = item.get("Id")

        if item_index not in self.updatingIndexesInProgress:
            self.updatingIndexesInProgress.append(item_index)

        image_index = -1
        req_width = -1
        req_height = -1
        if self.type == "chapters":
            image_index = item.get("ChapterIndex", -1)
            req_width = self.iconWidth
            req_height = self.iconHeight

        icon_pix = yield EmbyApiClient.getItemImageAsync(widget_id=self.widget_id, item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight,
                                                         image_type=self.icon_type, image_index=image_index, req_width=req_width, req_height=req_height, orig_item_id=orig_item_id)
        if not icon_pix and self.type != "chapters":
            backdrop_image_tags = item.get("BackdropImageTags")
            parent_backdrop_image_tags = item.get("ParentBackdropImageTags")
            if parent_backdrop_image_tags:
                backdrop_image_tags = parent_backdrop_image_tags

            if not backdrop_image_tags or len(backdrop_image_tags) == 0:
                returnValue(False)

            icon_img = backdrop_image_tags[0]
            parent_b_item_id = item.get("ParentBackdropItemId")
            if parent_b_item_id:
                item_id = parent_b_item_id

            if not icon_pix:
                icon_pix = yield EmbyApiClient.getItemImageAsync(widget_id=self.widget_id,
                                                                 item_id=item_id, logo_tag=icon_img, width=self.iconWidth, height=self.iconHeight, image_type="Backdrop")

        if orig_item_id not in self.thumbs:
            self.thumbs[orig_item_id] = icon_pix or True

        if item_index in self.updatingIndexesInProgress:
            self.updatingIndexesInProgress.remove(item_index)

        if icon_pix:
            DIRECTORY_PARSER.addToSet(icon_pix)
            self.instance.redrawItemByIndex(item_index)
        returnValue(True)

    def buildEntry(self, item_index, item, item_name, item_icon, played_perc, has_backdrop):
        xPos = 0
        yPos = 0
        res = [None]
        selected = self.selectedIndex == item_index
        item_id = item.get("Id")
        if item_id in self.thumbs:
            item_icon = self.thumbs[item_id]
        if selected and self.selectionEnabled:
            res.append(MultiContentEntryRectangle(
                pos=(self.spacing_sides - 3, self.spacing_sides - 3), size=(self.iconWidth + 6, self.iconHeight + 6),
                cornerRadius=8,
                backgroundColor=0x32772b, backgroundColorSelected=0x32772b))
        res.append(MultiContentEntryRectangle(
            pos=(self.spacing_sides, self.spacing_sides),
            size=(self.iconWidth, self.iconHeight),
            cornerRadius=6,
            backgroundColor=0x00222222))
        is_icon = not isinstance(item_icon, bool)
        if item_icon and is_icon:
            flags = 0
            if self.type == "cast":
                flags = BT_HALIGN_CENTER | BT_VALIGN_CENTER
            res.append(MultiContentEntryPixmapAlphaBlend(
                pos=(self.spacing_sides, self.spacing_sides),
                size=(self.iconWidth, self.iconHeight),
                png=LoadPixmap(item_icon),
                backcolor=None, backcolor_sel=None,
                cornerRadius=6,
                flags=flags))
        else:
            found = any(item_index in tup for tup in self.itemsForThumbs)
            if is_icon and not found:
                self.itemsForThumbs.append((item_index, item))
            if len(self.itemsForThumbs) > 0 and not self.running:
                threads.deferToThread(self.runQueueProcess)

        played_perc = int(played_perc)
        cornerEdges = 12
        if played_perc < 90:
            cornerEdges = 4
        if played_perc > 0:
            res.append(MultiContentEntryProgress(
                pos=(self.spacing_sides, self.spacing_sides + self.iconHeight - 6), size=(self.iconWidth, 6),
                percent=played_perc, foreColor=0x32772b, foreColorSelected=0x32772b, borderWidth=0, cornerRadius=6, cornerEdges=cornerEdges
            ))

        if self.type == "episodes":
            res.append(MultiContentEntryText(
                pos=(self.spacing_sides, self.iconHeight + 32), size=(self.iconWidth, 25),
                font=0, flags=RT_HALIGN_LEFT | RT_BLEND,
                cornerRadius=6,
                text=item_name,
                color=0xffffff, color_sel=0xffffff))
            date_str = item.get("PremiereDate")
            desc = item.get("Overview", "")
            if date_str:
                desc = f"{embyDateToString(date_str, "Episode")}  {convert_ticks_to_time(item.get("RunTimeTicks"))}\n{desc}"
            y = self.iconHeight + 32 + 25 + 5
            res.append(MultiContentEntryText(
                pos=(self.spacing_sides, y), size=(
                    self.iconWidth, self.itemHeight - y),
                font=0, flags=RT_HALIGN_LEFT | RT_BLEND | RT_WRAP,
                cornerRadius=6,
                text=desc,
                color=0x666666, color_sel=0x666666))
        else:
            res.append(MultiContentEntryText(
                pos=(self.spacing_sides, self.iconHeight + 32), size=(self.iconWidth, 70),
                font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_WRAP,
                cornerRadius=6,
                text=item_name,
                color=0xffffff, color_sel=0xffffff))

        played = item.get("UserData", {}).get("Played", False)
        unplayed_items_count = int(item.get(
            "UserData", {}).get("UnplayedItemCount", -1))
        if played:
            res.append(MultiContentEntryRectangle(
                pos=(self.spacing_sides + self.iconWidth - 45, self.spacing_sides),
                size=(45, 45),
                cornerRadius=6,
                cornerEdges=2 | 4,
                backgroundColor=0x32772b))
            res.append(MultiContentEntryPixmapAlphaBlend(
                pos=(self.spacing_sides + self.iconWidth - 45, self.spacing_sides),
                size=(45, 45),
                png=self.check24,
                backcolor=None, backcolor_sel=None,
                cornerRadius=6,
                flags=BT_HALIGN_CENTER | BT_VALIGN_CENTER))
        elif unplayed_items_count > 0:
            res.append(MultiContentEntryRectangle(
                pos=(self.spacing_sides + self.iconWidth - 45, self.spacing_sides),
                size=(45, 45),
                cornerRadius=6,
                cornerEdges=2 | 4,
                backgroundColor=0x32772b))
            res.append(MultiContentEntryText(
                pos=(self.spacing_sides + self.iconWidth - 45, self.spacing_sides), size=(45, 45),
                font=1, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
                cornerRadius=6,
                text=str(unplayed_items_count),
                color=0xffffff, color_sel=0xffffff))

        return res
