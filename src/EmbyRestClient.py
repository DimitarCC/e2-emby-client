from .Variables import REQUEST_USER_AGENT
from Tools.LoadPixmap import LoadPixmap
import urllib
import json
import requests
import os
from PIL import Image


class EmbyRestClient():
    def __init__(self, server_root_url, device_name, device_id):
        self.server_root = server_root_url
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

    def authorizeUser(self, username, password):
        if self.access_token:
            return

        payload = {
			'Username': username,
			'Pw': password
		}
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = self.constructRequest(f"{self.server_root}/emby/Users/AuthenticateByName", data)
        try:
            response = urllib.request.urlopen(req, timeout=10)  # set a timeout to prevent blocking
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

    def getItems(self, type_part, sortBy, includeItems, parent_part):
        items = {}
        req = self.constructRequest(f"{self.server_root}/emby/Users/{self.user_id}/Items{type_part}?Limit=40&SortBy={sortBy}&SortOrder=Descending&Fields=Overview,Genres,CriticRating,OfficialRating,Width,Height,CommunityRating,MediaStreams,PremiereDate&IncludeItemTypes={includeItems}{parent_part}")
        try:
            response = urllib.request.urlopen(req, timeout=10)  # set a timeout to prevent blocking
            response_obj = response.read()
            res_json_obj = json.loads(response_obj)
            items = res_json_obj.get('Items')
        except:
            pass
        return items

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
        response = requests.get(logo_url)
        if response.status_code != 404:
            im_tmp_path = "/tmp/emby/%s.%s" % (logo_tag, format)
            with open(im_tmp_path, "wb") as f:
                f.write(response.content)

            if alpha_channel:
                im = Image.open(im_tmp_path).convert("RGBA")
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
        return None


# here enter the server URL, Device name and device id
EmbyApiClient = EmbyRestClient("http://192.168.1.121:8096", "GBQuad4KPro", "gbquad4kpro")