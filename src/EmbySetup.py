from Components.ActionMap import HelpableActionMap
from Components.config import config, ConfigSelection, ConfigSubsection, ConfigSubList, ConfigInteger, ConfigYesNo, ConfigText, ConfigIP

from Components.Sources.StaticText import StaticText
from Screens.Setup import Setup
from Tools.BoundFunction import boundFunction

retries = 0


def initConnection(index):
	config.plugins.e2embyclient.connections.append(ConfigSubsection())
	config.plugins.e2embyclient.connections[index].name = ConfigText(default="Server", visible_width=50, fixed_size=False)
	config.plugins.e2embyclient.connections[index].ip = ConfigText(default="https://ip")
	config.plugins.e2embyclient.connections[index].port = ConfigInteger(default=8096, limits=(1, 65555))
	config.plugins.e2embyclient.connections[index].user = ConfigText(default="user", visible_width=50, fixed_size=False)
	config.plugins.e2embyclient.connections[index].password = ConfigText(default="password", visible_width=50, fixed_size=False)
	return config.plugins.e2embyclient.connections[index]


def initConfig():
	config.plugins.e2embyclient = ConfigSubsection()
	config.plugins.e2embyclient.conretries = ConfigInteger(default=5, limits=(5, 20))
	config.plugins.e2embyclient.dummy = ConfigYesNo(default=False)
	config.plugins.e2embyclient.connectioncount = ConfigInteger(0)
	config.plugins.e2embyclient.activeconnection = ConfigInteger(0)
	config.plugins.e2embyclient.connections = ConfigSubList()
	for idx in range(config.plugins.e2embyclient.connectioncount.value):
		initConnection(idx)
	retries = config.plugins.e2embyclient.conretries.value


def getActiveConnection():
	try:
		name = config.plugins.e2embyclient.connections[config.plugins.e2embyclient.activeconnection.value].name.value
		url = config.plugins.e2embyclient.connections[config.plugins.e2embyclient.activeconnection.value].ip.value
		port = config.plugins.e2embyclient.connections[config.plugins.e2embyclient.activeconnection.value].port.value
		username = config.plugins.e2embyclient.connections[config.plugins.e2embyclient.activeconnection.value].user.value
		password = config.plugins.e2embyclient.connections[config.plugins.e2embyclient.activeconnection.value].password.value
		return (name, url, port, username, password)
	except:
		return ("", "", 0, "", "")


class EmbySetup(Setup):
	def __init__(self, session, args=None):
		self.connections = []
		self.connectionItems = []
		self.createItems()
		Setup.__init__(self, session, "e2embyclient", plugin="Extensions/E2EmbyClient", PluginLanguageDomain="e2embyclient")
		self["key_yellow"] = StaticText(_("Add"))
		self["key_blue"] = StaticText(_("Remove"))
		self["selectEntriesActions"] = HelpableActionMap(self, ["ColorActions"],
		{
			"yellow": (self.keyYellow, _("Add Connection")),
			"blue": (self.keyBlue, _("Remove Connection"))
		}, prio=0, description=_("Setup Actions"))

	def updateButtons(self):
		current = self["config"].getCurrent()
		if current:
			if len(current) > 3:
				self["key_yellow"].setText(_("Edit"))
				self["key_blue"].setText(_("Remove"))
			else:
				self["key_yellow"].setText(_("Add"))
				self["key_blue"].setText("")
			self["selectEntriesActions"].setEnabled(True)
		else:
			self["selectEntriesActions"].setEnabled(False)

	def createItems(self):
		self.connectionItems = []
		for index in range(config.plugins.e2embyclient.connectioncount.value):
			item = config.plugins.e2embyclient.connections[index]
			self.connectionItems.append((f"{item.name.value}", ConfigYesNo(default=config.plugins.e2embyclient.activeconnection.value == index), "", index, item))

	def createSetup(self):  # NOSONAR silence S2638
		Setup.createSetup(self)
		self.list = self.list + self.connectionItems
		currentItem = self["config"].getCurrent()
		self["config"].setList(self.list)
		self.moveToItem(currentItem)

	def selectionChanged(self):
		self.updateButtons()
		Setup.selectionChanged(self)

	def calculateActive(self, index, active):
		config.plugins.e2embyclient.activeconnection.value = index if active else 0
		config.plugins.e2embyclient.activeconnection.save()
		config.plugins.e2embyclient.save()
		self.createItems()
		self.createSetup()

	def changedEntry(self):
		current = self["config"].getCurrent()
		if current and len(current) == 5:
			self.calculateActive(current[3], current[1].value)
			return
		Setup.changedEntry(self)

	def keyBlue(self):
		current = self["config"].getCurrent()
		if current and len(current) == 5:  # Remove
			config.plugins.e2embyclient.connections.remove(current[4])
			config.plugins.e2embyclient.connections.save()
			config.plugins.e2embyclient.connectioncount.value = len(config.plugins.e2embyclient.connections)
			config.plugins.e2embyclient.connectioncount.save()
			self.calculateActive(0, True)

	def keyYellow(self):
		def connectionCallback(index, result=None):
			if result:
				config.plugins.e2embyclient.connections[index] = result
				config.plugins.e2embyclient.connections.save()
				config.plugins.e2embyclient.connectioncount.value = index + 1
				config.plugins.e2embyclient.connectioncount.save()
				self.calculateActive(index, True)

		current = self["config"].getCurrent()
		if current and len(current) == 5:  # Edit
			currentItem = current[4]
			index = config.plugins.e2embyclient.connections.index(currentItem)
		else:  # Add
			index = len(config.plugins.e2embyclient.connections)
			currentItem = initConnection(index)
		self.session.openWithCallback(boundFunction(connectionCallback, index), EmbyConnections, currentItem)


class EmbyConnections(Setup):
	def __init__(self, session, entry):
		self.entry = entry
		Setup.__init__(self, session, "e2embyclientconnection", plugin="Extensions/E2EmbyClient", PluginLanguageDomain="e2embyclient")

	def keySave(self):
		Setup.saveAll(self)
		self.close(self.entry)
