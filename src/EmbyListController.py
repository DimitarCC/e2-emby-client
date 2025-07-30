class EmbyListController():
    def __init__(self, list, header):
        self.list = list
        self.header = header

    def move(self, x, y):
        self.header.move(x + 15, y)
        self.list.move(x, y + 40)
        return self

    def visible(self, visible):
        if visible:
            self.header.instance.show()
            self.list.instance.show()
        else:
            self.header.instance.hide()
            self.list.instance.hide()
        return self

    def enableSelection(self, enable):
        self.list.toggleSelection(enable)
        return self

    def getHeight(self):
        return self.list.instance.size().height() + 40
