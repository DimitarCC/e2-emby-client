class EmbyListController():
	def __init__(self, list, header, yOffset=0):
		self.yOffset = yOffset
		self.list = list
		self.header = header

	def setHeaderText(self, text):
		self.header.text = text
		return self

	def move(self, x, y):
		header_h = self.header.instance.size().height() + 10 if self.header else 0
		if self.header:
			self.header.move(x + 15, y + self.yOffset)
		self.list.move(x, y + self.yOffset + header_h)
		return self

	def getTopLeftCornerPos(self):
		widget = self.header
		if not widget:
			widget = self.list
		return widget.instance.position().x(), widget.instance.position().y()

	def visible(self, visible):
		if visible:
			if self.header:
				self.header.instance.show()
			self.list.instance.show()
		else:
			if self.header:
				self.header.instance.hide()
			self.list.instance.hide()
		return self

	def enableSelection(self, enable):
		self.list.toggleSelection(enable)
		return self

	def getHeight(self):
		return self.list.instance.size().height() + (40 if not self.header else self.header.instance.size().height() + 10)
