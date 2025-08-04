import urllib
import urllib.error
import socket
import json
import requests
import os
import random
from Tools.LoadPixmap import LoadPixmap
from Components.SystemInfo import BoxInfo
from Components.config import config
from PIL import Image

from .Variables import REQUEST_USER_AGENT



class EmbyRestClient():
	def __init__(self, device_name, device_id):
		self.server_root = ""
		self.access_token = None
		self.user_id = None
		self.device_name = device_name
		self.device_id = device_id

	def constructRequest(self, url, data=None):
		headers = {'User-Agent': REQUEST_USER_AGENT}
		headers["X-Emby-Authorization"] = f'Emby UserId="", Client="Enigma2Emby", Device="{self.device_name}", DeviceId="{self.device_id}", Version="1.0.0"'
		if self.access_token:
			headers["X-Emby-Token"] = self.access_token
		req = urllib.request.Request(url, headers=headers, data=data)
		return req

	def authorizeUser(self, server_url, server_port, username, password):
		self.server_root = f"{server_url}:{server_port}"
		if self.access_token:
			return

		payload = {
			'Username': username,
			'Pw': password
		}
		data = urllib.parse.urlencode(payload).encode('utf-8')
		req = self.constructRequest(f"{self.server_root}/emby/Users/AuthenticateByName", data)
		try:
			response = urllib.request.urlopen(req, timeout=4)  # set a timeout to prevent blocking
			status_code = response.getcode()
			if status_code == 200 or status_code == 204:
				auth_response = response.read().decode('utf-8')
				auth_json_obj = json.loads(auth_response)
				self.user_id = auth_json_obj.get('User', {}).get('Id', None)
				self.access_token = auth_json_obj.get('AccessToken', None)
		except:
			pass

	def getLibraries(self):
		libs = {}
		if self.access_token:
			req_libs = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Views")
			try:
				response_libs = urllib.request.urlopen(req_libs, timeout=10)  # set a timeout to prevent blocking
				libs_response = response_libs.read()
				libs_json_obj = json.loads(libs_response)
				libs = libs_json_obj.get('Items')
			except:
				pass
		return libs

	def getItems(self, type_part, sortBy, includeItems, parent_part, limit=40):
		items = {}
		req = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Items{type_part}?Limit={limit}&SortBy={sortBy}&SortOrder=Descending&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate,DateCreated&IncludeItemTypes={includeItems}{parent_part}")
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = urllib.request.urlopen(req, timeout=4)  # set a timeout to prevent blocking
				response_obj = response.read()
				res_json_obj = json.loads(response_obj)
				items = res_json_obj.get('Items')
				break
			except urllib.error.URLError as e:
				if not isinstance(e.reason, socket.timeout):
					break  # Non-timeout error: Don't retry
			except:
				break
		return items
	
	def getBoxsetsFromLibrary(self, library_id):
		items = []
		req = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&SortBy=SortName&SortOrder=Ascending&IncludeItemTypes=BoxSet&CollapseBoxSetItems=true&ParentId={library_id}&Fields=Genres,SortName,Path,Overview,RunTimeTicks,ProviderIds,DateCreated&Filter=IsFolder")
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = urllib.request.urlopen(req, timeout=4)  # set a timeout to prevent blocking
				response_obj = response.read()
				res_json_obj = json.loads(response_obj)
				items.extend(res_json_obj.get('Items'))
				break
			except urllib.error.URLError as e:
				if not isinstance(e.reason, socket.timeout):
					break  # Non-timeout error: Don't retry
			except:
				break
		return items
	
	def getBoxsetsChildren(self, boxset_id):
		items = []
		req = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&ParentId={boxset_id}")
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = urllib.request.urlopen(req, timeout=4)  # set a timeout to prevent blocking
				response_obj = response.read()
				res_json_obj = json.loads(response_obj)
				items.extend(res_json_obj.get('Items'))
				break
			except urllib.error.URLError as e:
				if not isinstance(e.reason, socket.timeout):
					break  # Non-timeout error: Don't retry
			except:
				break
		return items

	def getItemsFromLibrary(self, library_id, shouldShowBoxsets = True):
		items = []
		req = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Items?Recursive=true&SortBy=SortName&SortOrder=Ascending&IncludeItemTypes=Movie,Series&ParentId={library_id}&GroupItemsIntoCollections={'true' if shouldShowBoxsets else 'false'}&Fields=SortName,RunTimeTicks,DateCreated,ParentId")
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = urllib.request.urlopen(req, timeout=4)  # set a timeout to prevent blocking
				response_obj = response.read()
				res_json_obj = json.loads(response_obj)
				items.extend(res_json_obj.get('Items'))
				break
			except urllib.error.URLError as e:
				if not isinstance(e.reason, socket.timeout):
					break  # Non-timeout error: Don't retry
			except:
				break
		
		sorted_items = sorted(items, key=lambda x: x.get("SortName"))
		return sorted_items

	def getRandomItemFromLibrary(self, parent_id, type, limit=200):
		includeItems = "Movie"
		if type == "movies":
			includeItems = "Movie&IsMovie=true&Recursive=true&Filters=IsNotFolder"
		elif type == "tvshows":
			includeItems = "Series&IsFolder=true&Recursive=true"
		items = self.getItems("", "DateCreated", includeItems, f"&ParentId={parent_id}", limit)
		return items and random.choice(items) or {}

	def getItemImage(self, item_id, logo_tag, image_type, width=-1, height=-1, max_width=-1, max_height=-1, format="jpg", image_index=-1, alpha_channel=None):
		addon = ""
		if width > 0:
			addon += f"&Width={width}"
		if height > 0:
			addon += f"&Height={height}"
		if max_width > 0:
			addon += f"&MaxWidth={max_width}"
		if max_height > 0:
			addon += f"&MaxHeight={max_height}"
		if image_type == "Backdrop":
			if image_index > -1:
				image_type = f"{image_type}/{image_index}"
			else:
				image_type = f"{image_type}/0"

		logo_url = f"{self.server_root}/emby/Items/{item_id}/Images/{image_type}?tag={logo_tag}&format={format}{addon}"
		for attempt in range(config.plugins.e2embyclient.conretries.value):
			try:
				response = requests.get(logo_url, timeout=20)
				if response.status_code != 404:
					im_tmp_path = "/tmp/emby/%s.%s" % (logo_tag, format)
					with open(im_tmp_path, "wb") as f:
						f.write(response.content)

					if alpha_channel:
						im = Image.open(im_tmp_path).convert("RGBA")
						im_width, im_height = im.size
						required_height = im_width // 1.77
						if im_height > required_height:
							im = im.crop((0, 0, im_width, required_height))
						if alpha_channel.size != im.size:
							alpha_channel = alpha_channel.resize(im.size, Image.BOX)
						im.putalpha(alpha_channel)
						im.save("/tmp/emby/backdrop.png", compress_type=3)
						pix = LoadPixmap("/tmp/emby/backdrop.png")
					else:
						pix = LoadPixmap(im_tmp_path)
					try:
						os.remove(im_tmp_path)
					except:
						pass
					return pix
			except requests.exceptions.ReadTimeout:
				pass
			except:
				pass
		return None


# here enter the server URL, Device name and device id
EmbyApiClient = EmbyRestClient(BoxInfo.getItem("displaymodel"), BoxInfo.getItem("model"))
