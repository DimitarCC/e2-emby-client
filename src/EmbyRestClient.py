from json import loads
from os import remove, scandir
from requests import get, post, delete
from requests.exceptions import ReadTimeout
from secrets import choice
from urllib.parse import quote

from Components.config import config
from Components.SystemInfo import BoxInfo
from Tools.LoadPixmap import LoadPixmap

from .Variables import REQUEST_USER_AGENT, EMBY_THUMB_CACHE_DIR
from .HelperFunctions import crop_image_from_bytes, resize_and_center_image

from PIL import Image


class DirectoryParser:
	def __init__(self):
		self.THUMBS = set()

	def listDirectory(self):
		if config.plugins.e2embyclient.thumbcache_loc.value == "off":
			return
		self.THUMBS = set([entry.path for entry in scandir(f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}") if entry.is_file()])

	def addToSet(self, item):
		if config.plugins.e2embyclient.thumbcache_loc.value == "off":
			return
		self.THUMBS.add(item)

	def removeFromSet(self, item):
		if config.plugins.e2embyclient.thumbcache_loc.value == "off":
			return
		self.THUMBS.remove(item)


DIRECTORY_PARSER = DirectoryParser()


class EmbyRestClient():
	def __init__(self, device_name, device_id):
		self.server_root = ""
		self.access_token = None
		self.user_id = None
		self.device_name = device_name
		self.device_id = device_id
		self.userSettings = {}

	def constructHeaders(self):
		headers = {'User-Agent': REQUEST_USER_AGENT}
		headers["X-Emby-Authorization"] = f'Emby UserId="", Client="Enigma2Emby", Device="{self.device_name}", DeviceId="{self.device_id}", Version="1.0.0"'
		if self.access_token:
			headers["X-Emby-Token"] = self.access_token
		return headers

	def authorizeUser(self, server_url, server_port, username, password):
		self.server_root = f"{server_url}:{server_port}"
		if self.access_token:
			return

		headers = self.constructHeaders()
		payload = {
			'Username': username,
			'Pw': password
		}

		url = f"{self.server_root}/emby/Users/AuthenticateByName"
		try:
			# set a timeout to prevent blocking
			response = post(url, headers=headers, data=payload, timeout=10)
			status_code = response.status_code
			if status_code == 200 or status_code == 204:
				auth_response = response.content
				auth_json_obj = loads(auth_response)
				self.user_id = auth_json_obj.get('User', {}).get('Id', None)
				self.access_token = auth_json_obj.get('AccessToken', None)
				url = f"{self.server_root}/emby/UserSettings/{self.user_id}"
				try:
					headers = self.constructHeaders()
					response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
					status_code = response.status_code
					if status_code == 200 or status_code == 204:
						response_str = response.content
						self.userSettings = loads(response_str)
				except:
					pass
		except:
			pass

	def getLibraries(self):
		libs = {}
		headers = self.constructHeaders()
		if self.access_token:
			url = f"{self.server_root}/emby/Users/{self.user_id}/Views"
			try:
				response_libs = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				libs_response = response_libs.content
				libs_json_obj = loads(libs_response)
				libs = libs_json_obj.get('Items')
			except:
				pass
		return libs

	def getItems(self, type_part, sortBy, includeItems, parent_part, loadFullInfo=False, limit=40):
		items = {}
		headers = self.constructHeaders()
		includeItemsParam = "IncludeItemTypes="
		if type_part == "/Resume":
			includeItemsParam = "MediaTypes="
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items{type_part}?Limit={limit}&SortBy={sortBy}&SortOrder=Descending&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,EndDate,DateCreated,Status,ChildCount{',Chapters,Taglines,People' if loadFullInfo else ''}&{includeItemsParam}{includeItems}{parent_part}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				res_json_obj = loads(response_obj)
				items = res_json_obj.get('Items')
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getResumableItemsForLibrary(self, library_id, library_type, limit=40):
		items = {}
		headers = self.constructHeaders()
		include_items = ""
		if library_type == "movies":
			include_items = "Movie"
		elif library_type == "tvshow":
			include_items = "Episode"
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items/Resume?IncludeItemTypes={include_items}&MediaTypes=Video&ParentId={library_id}&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,DateCreated&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				res_json_obj = loads(response_obj)
				items = res_json_obj.get('Items')
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getRecentlyAddedItemsForLibrary(self, library_id, limit=40):
		items = {}
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items/Latest?ParentId={library_id}&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,DateCreated&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				items = loads(response_obj)
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getRecentlyReleasedItemsForLibrary(self, library_id, library_type, limit=40):
		items = {}
		headers = self.constructHeaders()
		include_items = ""
		if library_type == "movies":
			include_items = "Movie"
		elif library_type == "tvshow":
			include_items = "Episode"
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&IncludeItemTypes={include_items}&ParentId={library_id}&SortBy=PremiereDate&SortOrder=Descending&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,DateCreated&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				res_json_obj = loads(response_obj)
				items = res_json_obj.get('Items')
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getSingleItem(self, item_id):
		item = {}
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items/{item_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				item = loads(response_obj)
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return item

	def getEpisodesForSeries(self, item_id):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Shows/{item_id}/Episodes?UserId={self.user_id}&Fields=Overview"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				json_obj = loads(response_obj)
				items.extend(json_obj.get("Items", []))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getSeasonsForSeries(self, item_id):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Shows/{item_id}/Seasons?UserId={self.user_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				json_obj = loads(response_obj)
				items.extend(json_obj.get("Items", []))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getBoxsetsForItem(self, item_id, limit=40):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items?IncludeItemTypes=Playlist%2CBoxSet&Recursive=true&SortBy=SortName&ListItemIds={item_id}&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				items.extend(loads(response_obj))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getSimilarMoviesForItem(self, item_id, limit=40):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Movies/{item_id}/Similar?UserId={self.user_id}&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				items.extend(loads(response_obj))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getSimilarSeriesForItem(self, item_id, limit=40):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Shows/{item_id}/Similar?UserId={self.user_id}&Limit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					response_obj = response.content
					items.extend(loads(response_obj))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getExtrasForItem(self, item_id, limit=40):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items/{item_id}/SpecialFeatures"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					response_obj = response.content
					items.extend(loads(response_obj))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getBoxsetsFromLibrary(self, library_id):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&SortBy=SortName&SortOrder=Ascending&IncludeItemTypes=BoxSet&CollapseBoxSetItems=true&ParentId={library_id}&Fields=Genres,SortName,Path,Overview,RunTimeTicks,ProviderIds,DateCreated&Filter=IsFolder"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					response_obj = response.content
					res_json_obj = loads(response_obj)
					items.extend(res_json_obj.get('Items'))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getBoxsetsChildren(self, boxset_id):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&IncludeItemTypes=Movie&ParentId={boxset_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					response_obj = response.content
					res_json_obj = loads(response_obj)
					items.extend(res_json_obj.get('Items'))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getItemsFromLibrary(self, library_id):
		shouldShowBoxsets = self.userSettings.get(
			f"{library_id}-1-videos-groupItemsIntoCollections", "false") == "true"
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&SortBy=SortName&SortOrder=Ascending&IncludeItemTypes=Movie,Series&ParentId={library_id}&GroupItemsIntoCollections={'true' if shouldShowBoxsets else 'false'}&Fields=SortName,PremiereDate,DateCreated"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					response_obj = response.content
					res_json_obj = loads(response_obj)
					items.extend(res_json_obj.get('Items'))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break

		# sorted_items = sorted(items, key=lambda x: x.get("SortName"))
		return items  # sorted_items

	def getRandomItemFromLibrary(self, parent_id, type, limit=2000):
		includeItems = "Movie"
		if type == "movies":
			includeItems = "Movie&IsMovie=true&Recursive=true&Filters=IsNotFolder"
		elif type == "tvshows":
			includeItems = "Series&IsFolder=true&Recursive=true"
		items = self.getItems("", "DateCreated", includeItems, f"&ParentId={parent_id}", limit)
		return items and choice(items) or {}

	def getRecommendedMoviesForLibrary(self, library_id, limit=40):
		items = []
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Movies/Recommendations?UserId={self.user_id}&categoryLimit=6&GroupProgramsBySeries=true&ParentId={library_id}&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,DateCreated&ItemLimit={limit}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				response_obj = response.content
				items.extend(loads(response_obj))
				break
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return items

	def getItemImage(self, item_id, logo_tag, image_type, width=-1, height=-1, max_width=-1, max_height=-1, format="jpg", image_index=-1, alpha_channel=None, req_width=-1, req_height=-1, orig_item_id="", widget_id=""):
		filename_suffix = ""

		addon = ""
		orig_image_type = image_type
		file_addon = ""

		if width > 0:
			addon += f"&Width={width}"
			filename_suffix += f"_{width}"
			file_addon += f"{width}"
		if height > 0:
			addon += f"&Height={height}"
			filename_suffix += f"_{height}"
			file_addon += f"x{height}"
		if max_width > 0:
			addon += f"&MaxWidth={max_width}"
			filename_suffix += f"_{max_width}"
		if max_height > 0:
			addon += f"&MaxHeight={max_height}"
			filename_suffix += f"_{max_height}"

		if image_type in ["Backdrop", "Chapter"]:
			image_type = f"{image_type}/{image_index if image_index > -1 else 0}"

		logo_url = f"{self.server_root}/emby/Items/{item_id}/Images/{image_type}?tag={logo_tag}&quality=60&format={format}{addon}"
		im_tmp_path = ""
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(logo_url, timeout=(
					config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					filename = logo_tag
					if orig_image_type == "Chapter":
						filename = f"{filename}_{image_index}"

					if config.plugins.e2embyclient.thumbcache_loc.value == "/tmp":
						im_tmp_path = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{widget_id}/{orig_item_id or item_id}_{file_addon}_{filename}_{orig_item_id}.{format}"
					else:
						im_tmp_path = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{orig_item_id or item_id}_{file_addon}_{filename}_{filename_suffix}.{format}"
					if req_width > 0 and req_height > 0:
						resize_and_center_image(
							response.content, (req_width, req_height), im_tmp_path)
					else:
						with open(im_tmp_path, "wb") as f:
							f.write(response.content)

					if alpha_channel:
						im = Image.open(im_tmp_path).convert("RGBA")
						im_width, im_height = im.size
						required_height = im_width // 1.77
						if im_height > required_height:
							im = im.crop((0, 0, im_width, required_height))
						if alpha_channel.size != im.size:
							alpha_channel = alpha_channel.resize(
								im.size, Image.BOX)
						im.putalpha(alpha_channel)
						im.save(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop.png", compress_type=3)
						result = LoadPixmap(f"/tmp{EMBY_THUMB_CACHE_DIR}/backdrop.png")
					else:
						result = im_tmp_path if image_type != "Logo" else LoadPixmap(im_tmp_path)
					if image_type in ["Logo", "Backdrop"] or config.plugins.e2embyclient.thumbcache_loc.value == "off":
						try:
							remove(im_tmp_path)
						except:
							pass
					return result
				else:
					return None
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except Exception as ex:
				print("EXEPTION: " + str(ex))
		return None

	def getPersonImage(self, person_name, logo_tag, width=-1, height=-1, max_width=-1, max_height=-1, format="jpg", image_index=-1, req_width=-1, req_height=-1, widget_id=""):
		image_type = "Primary"
		addon = ""
		if width > 0:
			addon += f"&Width={width}"
		if height > 0:
			addon += f"&Height={height}"
		if max_width > 0:
			addon += f"&MaxWidth={max_width}"
		if max_height > 0:
			addon += f"&MaxHeight={max_height}"
		if image_index > -1:
			image_type = f"{image_type}/{image_index}"
		else:
			image_type = f"{image_type}/0"

		encoded = quote(person_name)
		logo_url = f"{self.server_root}/emby/Persons/{encoded}/Images/{image_type}?tag={logo_tag}&quality=60&format={format}{addon}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = get(logo_url, timeout=(
					config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				if response.status_code != 404:
					if config.plugins.e2embyclient.thumbcache_loc.value == "off":
						im_tmp_path = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{widget_id}/{logo_tag}.{format}"
					else:
						im_tmp_path = f"{config.plugins.e2embyclient.thumbcache_loc.value}{EMBY_THUMB_CACHE_DIR}/{logo_tag}.{format}"
					if req_width > 0 and req_height > 0:
						crop_image_from_bytes(
							response.content, req_width, req_height, im_tmp_path)
					else:
						with open(im_tmp_path, "wb") as f:
							f.write(response.content)
					pix = im_tmp_path
					if config.plugins.e2embyclient.thumbcache_loc.value == "off":
						try:
							remove(im_tmp_path)
						except:
							pass
					return pix
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				pass
		return None

	def sendWatched(self, item):
		item_id = item.get("Id")
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/PlayedItems/{item_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				post(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				return True, True
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return False, False

	def sendUnWatched(self, item):
		item_id = item.get("Id")
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/PlayedItems/{item_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				delete(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				return True, False
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return False, False

	def sendFavorite(self, item):
		item_id = item.get("Id")
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/FavoriteItems/{item_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				post(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				return True, True
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return False, False

	def sendNotFavorite(self, item):
		item_id = item.get("Id")
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Users/{self.user_id}/FavoriteItems/{item_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				delete(url, headers=headers, timeout=config.plugins.e2embyclient.con_timeout.value)
				return True, False
			except ReadTimeout:
				pass
			except:
				break
		return False, False

	def updateTimeProgress(self, playSessionId, item_id, media_source_id, aIndex, sIndex, pos):
		self.updateProgress(playSessionId, item_id, media_source_id, "TimeUpdate", aIndex, sIndex, pos)

	def updateProgress(self, playSessionId, item_id, media_source_id, event, aIndex, sIndex, pos):
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Sessions/Playing/Progress?reqformat=json"
		post_data = {}
		post_data["ItemId"] = item_id
		post_data["MediaSourceId"] = media_source_id
		post_data["PlaySessionId"] = playSessionId
		post_data["EventName"] = event
		post_data["AudioStreamIndex"] = aIndex
		post_data["IsPaused"] = event == "Pause"
		if sIndex > -1:
			post_data["SubtitleStreamIndex"] = sIndex
		post_data["PositionTicks"] = pos
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				post(url, headers=headers, json=post_data, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break

	def setPlaySessionParameters(self, playSessionId, item_id, media_source_id, defAudioIndex, defSubtitleIndex, playPos=-1, stopped=False):
		headers = self.constructHeaders()
		stoppedAddon = ""
		if stopped:
			stoppedAddon = "/Stopped"
		url = f"{self.server_root}/emby/Sessions/Playing{stoppedAddon}?reqformat=json"
		post_data = {}
		post_data["ItemId"] = item_id
		post_data["MediaSourceId"] = media_source_id
		post_data["PlaySessionId"] = playSessionId
		post_data["AudioStreamIndex"] = defAudioIndex + 1
		if playPos > -1:
			post_data["PositionTicks"] = playPos
		if defSubtitleIndex > -1:
			post_data["SubtitleStreamIndex"] = defSubtitleIndex
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				post(url, headers=headers, json=post_data, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break

	def getPlaySession(self, item_id, media_source_id, defAudioIndex, defSubtitleIndex):
		headers = self.constructHeaders()
		url = f"{self.server_root}/emby/Items/{item_id}/PlaybackInfo?UserId={self.user_id}&IsPlayback=true&AutoOpenLiveStream=true&AudioStreamIndex={defAudioIndex}&SubtitleStreamIndex={defSubtitleIndex}&MediaSourceId={media_source_id}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = post(url, headers=headers, timeout=(config.plugins.e2embyclient.con_timeout.value, config.plugins.e2embyclient.read_con_timeout.value))
				json = loads(response.content)
				playSessionId = json.get("PlaySessionId")
				return playSessionId
			except TimeoutError:
				pass
			except ReadTimeout:
				pass
			except:
				break
		return ""


EmbyApiClient = EmbyRestClient(BoxInfo.getItem("displaymodel"), BoxInfo.getItem("model"))
