from Tools.Directories import resolveFilename, SCOPE_CONFIG
from os import path

# General variables

# User Agents
USER_AGENTS = {"android": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.6834.79 Mobile Safari/537.36",
               "ios": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/132.0.6834.78 Mobile/15E148 Safari/604.1",
               "windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/131.0.2903.86",
               "vlc": "VLC/3.0.18 LibVLC/3.0.11"}

REQUEST_USER_AGENT = USER_AGENTS["windows"]
