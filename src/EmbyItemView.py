from . import _

from Components.Label import Label

from .EmbyList import EmbyList
from .EmbyListController import EmbyListController
from .EmbyItemViewBase import EmbyItemViewBase
from .HelperFunctions import convert_ticks_to_time
from .EmbyItemFunctionButtons import playItem


class EmbyItemView(EmbyItemViewBase):
    def __init__(self, session, item, backdrop=None):
        EmbyItemViewBase.__init__(self, session, item, backdrop)
        self["cast_header"] = Label(_("Cast and Crew"))
        self["list_cast"] = EmbyList(type="cast")
        self.cast_controller = EmbyListController(self["list_cast"], self["cast_header"])
        self.lists["list_cast"] = self.cast_controller
        self["chapters_header"] = Label(_("Chapters"))
        self["list_chapters"] = EmbyList(type="chapters")
        self.chapters_controller = EmbyListController(self["list_chapters"], self["chapters_header"])
        self.lists["list_chapters"] = self.chapters_controller
        self["header_extras"] = Label(_("Extras"))
        self["list_extras"] = EmbyList()
        self.extras_controller = EmbyListController(self["list_extras"], self["header_extras"])
        self.lists["list_extras"] = self.extras_controller

    def preLayoutFinished(self):
        self.lists["list_chapters"].visible(False)
        cast_header_y = self["cast_header"].instance.position().y()
        self.cast_controller.move(40, cast_header_y).visible(True).enableSelection(False)
        self.availableWidgets.append("list_cast")

    def processItem(self):
        EmbyItemViewBase.processItem(self)
        if self.selected_widget == "list_chapters":
            chapter = self["list_chapters"].selectedItem
            startPos = int(chapter.get("StartPositionTicks", "0")) / 10_000_000
            playItem(self.item, self.session, callback=self.playerExitCallback, startPos=startPos)

    def playerExitCallback(self, *result):
        self.onPlayerClosedResult()
        self.loadItemInUI(self.loadItemInfoFromServer(self.item_id))

    def injectAfterLoad(self, item):
        cast_crew_list = item.get("People", [])
        list = []
        if cast_crew_list:
            i = 0
            for cr in cast_crew_list:
                list.append((i, cr, f"{cr.get('Name')}\n({cr.get("Role", cr.get("Type"))})", None, "0", True))
                i += 1
            self["list_cast"].loadData(list)
            self.availableWidgets.append("list_cast")
        media_sources = item.get("MediaSources", [])
        default_media_source = next((ms for ms in media_sources if ms.get("Type") == "Default"), None)
        if default_media_source:
            chapters = default_media_source.get("Chapters", [])
            list = []
            if chapters:
                i = 0
                for ch in chapters:
                    pos_ticks = int(ch.get("StartPositionTicks"))
                    ch["Id"] = f"{item.get('Id')}_{ch.get("ChapterIndex")}"
                    list.append((i, ch, f"{ch.get('Name')}\n{convert_ticks_to_time(pos_ticks, True)}", None, "0", True))
                    i += 1
                self["list_chapters"].loadData(list)
                self.availableWidgets.append("list_chapters")
                self.lists["list_chapters"].visible(True)
            else:
                self.lists["list_chapters"].visible(False)
