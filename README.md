# E2EmbyClient

[![Ruff Linter](https://github.com/DimitarCC/e2-emby-client/actions/workflows/ruff.yml/badge.svg)](https://github.com/DimitarCC/e2-emby-client/actions/workflows/ruff.yml)
[![Pylint Code Check](https://github.com/DimitarCC/e2-emby-client/actions/workflows/pylint.yml/badge.svg)](https://github.com/DimitarCC/e2-emby-client/actions/workflows/pylint.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

A native [Emby](https://emby.media/) client plugin for Enigma2 set-top boxes. Browse your Emby libraries, play movies, series and live content, and control playback — all from your Enigma2 skin, using the box's own playback engine (GStreamer, HiPlayer or Exteplayer3).

## Features

- **Library browsing** — grid-based library screens for movies, series, box sets and episodes, with an alphabet/character jump bar for fast navigation.
- **Rich detail views** — dedicated info screens for movies, series, seasons and episodes (cast, plot, ratings, genres, media info, etc.).
- **Playback**
  - Resume, play from start, and play trailers.
  - Multiple video/audio version selection.
  - Audio and subtitle track switching, including non-UTF-8 subtitle encodings (Cyrillic, Japanese, Chinese, Arabic, ...).
  - Skip Intro button for content with intro markers.
  - Up Next screen with an autoplay countdown before the next episode.
  - Seek handling tuned per playback engine.
- **Item actions** — mark watched/unwatched, favorite/unfavorite, jump to parent series.
- **Theme music** playback while browsing a movie/series detail screen.
- **Notifications** for connection/playback errors and status.
- **Multiple server connections** — configure and switch between several Emby servers/users.
- **Thumbnail caching** to a temporary or persistent (HDD/USB) location, with automatic cleanup.
- **Translations** — currently includes Bulgarian (`bg`) and German (`de`) locales, alongside the English (default) source strings.

## Requirements

- Enigma2 image with an **FHD (1920×1080)** skin (the plugin refuses to start on lower resolutions).
- An [Emby Server](https://emby.media/) instance reachable from the box, plus a valid user account.
- Python 3 with the `pillow` and `requests` packages (installed automatically as dependencies of the `.ipk` package).
- Optional: the [ServiceApp](https://github.com/openpli/enigma2-plugin-systemplugins-serviceapp) plugin, if you want to use Exteplayer3 as the playback engine.

## Installation

### From a pre-built `.ipk`

1. Download the latest `enigma2-plugin-extensions-e2embyclient_*_all.ipk` (from a release or your feed).
2. Install it via your image's package manager, or manually:
   ```sh
   opkg install enigma2-plugin-extensions-e2embyclient_*_all.ipk
   ```
3. Restart the GUI (or the whole box) if prompted.

### Building the `.ipk` yourself

The [build.sh](build.sh) script packages [src/](src/) into a Debian-style `.ipk`:

```sh
./build.sh
```

Run it from Git Bash / MSYS2 on Windows (some additional packages, e.g. `ar.exe`, may be required), or any POSIX shell on Linux/macOS. It bumps the version using the current git revision/commit hash and produces `enigma2-plugin-extensions-e2embyclient_<version>_all.ipk` in the repository root.

### OpenEmbedded / feed integration

A BitBake recipe is provided at [enigma2-plugin-extensions-e2embyclient.bb](enigma2-plugin-extensions-e2embyclient.bb) for integrating the plugin into `oe-alliance-core` / `openpli-oe-core` based image feeds.

## Setup

1. Open **Menu → Plugins → Extensions → Emby Player** (or the main menu, if enabled in settings).
2. On first run (no connections configured yet) the plugin opens its setup screen automatically.
3. Add a connection with:
   - **Name** — a label for the server (freely chosen).
   - **URL** — root address of the Emby server (e.g. `https://192.168.1.10`).
   - **Port** — Emby server port (default `8096`).
   - **User** / **Password** — Emby account credentials.
4. Use the **yellow** button to add/edit and the **blue** button to remove connections, and toggle a connection's checkbox to make it the active one.

## Configuration

All settings are available under **Emby Player → Setup** and grouped as follows:

| Group | Setting | Description |
|---|---|---|
| Timeouts | Connection retries count | Number of retry attempts for failed connections. |
| | Connection timeout | Timeout (s) for establishing a connection. |
| | Connection read timeout | Timeout (s) for reading a response. |
| | Theme music settle delay | Delay (ms) after theme music stops before the next stream starts. |
| | Player initial seek delay | Delay (ms) before the player's first seek attempt. |
| | Player initial seek delay (Exteplayer3) | Same, tuned for Exteplayer3. |
| | Audio track change settle delay | Delay (ms) before re-checking the active audio track after a switch. |
| UI Settings | Thumb cache location | Where thumbnail cache is stored — temporary (`/tmp`) or a persistent mount. |
| | UI scroll delay | Delay between list selection-changed events. |
| | Add to Main Menu / Extensions Menu | Expose the plugin from the main/extensions menus. |
| | Stop playing service on home load | Stop the current live service while browsing, restoring it on exit. |
| | Play theme music | Play a movie/series' theme music on its detail screen. |
| Player Settings | Playback system | GStreamer, HiPlayer or Exteplayer3 (if ServiceApp is installed). |
| | Encoding for non-UTF-8 subtitles | Fallback character encoding for legacy subtitle files. |
| | Show Skip Intro button | Toggle the Skip Intro button during playback. |
| | Show Up Next screen | Toggle the autoplay Up Next screen between episodes. |
| Connections | — | Manage one or more Emby server connections (see [Setup](#setup)). |

## Project layout

```
src/                    Plugin package (installed to Plugins/Extensions/E2EmbyClient)
├── plugin.py           Plugin entry point / menu registration
├── EmbySetup.py        Configuration schema and setup screens
├── EmbyRestClient.py   Emby REST API client
├── EmbyHome.py         Home screen
├── EmbyLibraryScreen.py    Library grid screen
├── EmbyGridList.py / EmbyList.py   List/grid widgets
├── EmbyMovieItemView.py, EmbySeriesItemView.py,
│   EmbyEpisodeItemView.py, EmbyBoxSetItemView.py   Detail screens per item type
├── EmbyPlayer.py        Playback screen (seek, tracks, subtitles, skip intro, up next)
├── EmbyItemFunctionButtons.py   Play/watched/favorite/etc. action buttons
├── EmbyUpNextScreen.py, EmbySkipIntroScreen.py   Playback overlays
├── EmbyThemeMusic.py     Theme music playback
├── EmbyNotification.py   In-app notifications
├── HelperFunctions.py, Variables.py, Globals.py   Shared utilities/constants
├── keymap.xml, setup.xml     Enigma2 keymap and setup definitions
└── locale/               Translations (.po/.mo)

meta/                   Debian control files used by build.sh
CI/                     Linting/build helper scripts used in CI
po/                     Translation update scripts
```

## Development

- **Linting**: the project uses [Ruff](pyproject.toml) (`ruff check src`) and Pylint, both run in CI on every push/PR (see [.github/workflows](.github/workflows)).
- **Import sorting**: `isort` is configured in [pyproject.toml](pyproject.toml) (black profile, 120-char lines).
- **Translations**: run `python setup_translate.py` targets, or the scripts in [po/](po/), to update `.po`/`.mo` files after changing translatable strings.
- CI also includes an auto-tag workflow and a compile check ([.github/workflows](.github/workflows)) that verify the plugin byte-compiles cleanly.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).

## Links

- Homepage / source: https://github.com/DimitarCC/e2-emby-client
- Emby: https://emby.media/
