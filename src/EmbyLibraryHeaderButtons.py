from twisted.internet import threads
from enigma import eLabel, eListbox, eListboxPythonMultiContent, gFont, RT_VALIGN_CENTER, RT_HALIGN_LEFT, RT_HALIGN_CENTER, getDesktop, eSize, RT_BLEND
from skin import parseColor, parseFont

from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.MultiContent import MultiContentEntryText, MultiContentEntryRectangle

from . import _


class EmbyLibraryHeaderButtons(GUIComponent):
    def __init__(self, screen):
        GUIComponent.__init__(self)
        self.screen = screen
        self.buttons = []
        self.selectedIndex = 0
        self.focused = False
        self.selectionEnabled = True
        self.isMoveLeftRight = False
        self.screen.onShow.append(self.onContainerShown)
        self.data = []
        self.font = gFont("Regular", 22)
        self.fontAdditional = gFont("Regular", 22)
        self.foreColorAdditional = 0xffffff
        self.l = eListboxPythonMultiContent()  # noqa: E741
        self.l.setBuildFunc(self.buildEntry)
        self.spacing = 10
        self.drawing_start_x = -1
        self.container_rect_width = -1

        self.orientation = eListbox.orHorizontal
        self.l.setItemHeight(35)
        self.l.setItemWidth(35)

    GUI_WIDGET = eListbox

    def postWidgetCreate(self, instance):
        instance.setSelectionEnable(False)
        instance.setContent(self.l)
        instance.allowNativeKeys(False)

    def onContainerShown(self):
        self.l.setItemHeight(self.instance.size().height())
        self.l.setItemWidth(self.instance.size().width())

    def applySkin(self, desktop, parent):
        attribs = []
        for (attrib, value) in self.skinAttributes[:]:
            if attrib == "font":
                self.font = parseFont(value, parent.scale)
            elif attrib == "fontAdditional":
                self.fontAdditional = parseFont(value, parent.scale)
            elif attrib == "foregroundColor":
                self.foreColor = parseColor(value).argb()
            elif attrib == "foregroundColorAdditional":
                self.foreColorAdditional = parseColor(value).argb()
            elif attrib == "spacing":
                self.spacing = int(value)
            else:
                attribs.append((attrib, value))
        self.skinAttributes = attribs
        self.l.setFont(0, self.font)
        self.l.setFont(1, self.fontAdditional)
        self.instance.setOrientation(self.orientation)
        self.l.setOrientation(self.orientation)
        return GUIComponent.applySkin(self, desktop, parent)

    def setFocused(self, focused):
        self.focused = focused
        self.updateInfo()

    def moveSelection(self, dir):
        self.isMoveLeftRight = True
        nextPos = self.selectedIndex + dir
        if nextPos < 0 or nextPos >= len(self.buttons):
            return
        self.selectedIndex = nextPos
        self.updateInfo()

    def setSelectedIndex(self, index):
        self.selectedIndex = index
        self.updateInfo()

    def moveNext(self):
        self.moveSelection(1)

    def movePrevious(self):
        self.moveSelection(-1)

    def isAtHome(self):
        return self.selectedIndex == 0

    def isAtEnd(self):
        return self.selectedIndex == len(self.buttons) - 1

    def getSelectedButton(self):
        return self.buttons[self.selectedIndex]

    def setItem(self, item):
        self.buttons = []
        self.item = item
        type = item.get("CollectionType", None)
        if type == "movies":
            self.buttons.append(
                (len(self.buttons), _("Recommendations"), "recommend"))
            self.buttons.append((len(self.buttons), _("Movies"), "list"))
        else:
            self.buttons.append(
                (len(self.buttons), _("Recommendations"), "recommend"))
            self.buttons.append((len(self.buttons), _("Series"), "list"))

        self.updateInfo()

    def updateInfo(self):
        l_list = []
        l_list.append((self.buttons,))
        self.l.setList(l_list)

    def enableSelection(self, selection):
        if not selection:
            self.selectedIndex = 0
        self.selectionEnabled = selection
        self.isMoveLeftRight = False
        self.updateInfo()

    def _calcTextSize(self, text, font=None, size=None):
        size = eLabel.calculateTextSize(font, text, size)
        res_width = size.width()
        res_height = size.height()
        return res_width, res_height

    def getDesktopWith(self):
        return getDesktop(0).size().width()

    def getSize(self):
        s = self.instance.size()
        return s.width(), s.height()

    def constructButton(self, res, text, height, xPos, yPos, selected=False, spacing=None, backColorSelected=0x32772b, backColor=0x606060, textColor=0xffffff):
        if not spacing:
            spacing = self.spacing

        textWidth = self._calcTextSize(text, font=self.font, size=eSize(self.getDesktopWith() // 3, 0))[0]

        rec_height = height

        back_color = backColorSelected if selected else None
        offset = xPos + textWidth + height
        res.append(MultiContentEntryText(
            pos=(xPos - 1 - (2 if self.focused else 0), yPos + (1 if self.focused else 4)), size=(textWidth + height + (4 if self.focused else 0), rec_height - (2 if self.focused else 8)),
            font=0, flags=RT_HALIGN_CENTER | RT_BLEND | RT_VALIGN_CENTER,
            text=text,
            cornerRadius=((rec_height - (4 if self.focused else 8)) // 2) if (selected and self.focused) or selected else 0,
            border_width=2 if selected and self.focused else 0, border_color=0xffffff,
            backcolor=back_color, backcolor_sel=back_color,
            color=textColor, color_sel=textColor))
        offset += spacing
        return offset

    def buildEntry(self, buttons):
        xPos = 0
        yPos = 0
        height = self.instance.size().height()
        width = self.instance.size().width()
        if self.drawing_start_x > -1:
            xPos = self.drawing_start_x
        res = [None]

        if self.drawing_start_x > -1:
            res.append(MultiContentEntryRectangle(
                pos=(self.drawing_start_x - 4, 0), size=(self.container_rect_width, height),
                cornerRadius=(height // 2) - 2,
                backgroundColor=0x22333333, backgroundColorSelected=0x22333333))

        for button in buttons:
            selected = button[0] == self.selectedIndex
            xPos = self.constructButton(res, button[1], height, xPos, yPos, selected)

        if self.drawing_start_x == -1:
            self.drawing_start_x = (width - xPos) // 2
            self.container_rect_width = xPos - 3
            return self.buildEntry(buttons)

        # self.move((1920 - xPos) // 2, self.instance.position().y())

        return res
