# vdown

A fast, versatile command-line video and media downloader. Download videos, audio, streams, and direct media files from virtually any link on the web.

## Features

- **Interactive ASCII Art Hub**: Launch `vdown` to access a guided welcome screen with rich system diagnostics, tool statuses, and top-level menu selection.
- **IDM-Style Turbo Accelerator**: Parallel segmented multi-connection engine (4–32 concurrent streams via HTTP byte ranges) to bypass ISP and server bandwidth throttling on direct links.
- **BitTorrent & Magnet P2P Downloads**: High-speed peer-to-peer downloading for magnet links and `.torrent` files with DHT, peer swarm integration, and pure Python metadata inspection.
- **Universal Link Support**: Downloads from YouTube, Facebook, Instagram, TikTok (without watermark), Spotify, Twitter/X, Vimeo, Reddit, Twitch, and 1800+ other platforms.
- **Spotify Tracks & Playlists**: Download Spotify tracks, playlists, and albums in **FLAC Lossless**, **WAV PCM**, or **320 kbps MP3** with embedded tags and high-resolution album cover art.
- **YouTube Playlists**: Downloads complete playlists or specific track ranges into organized folders with track numbers (`01 - Title.mp4`).
- **Studio-Quality Audio Extraction**: Extract audio in lossless **FLAC** (bit-perfect studio quality), **320 kbps MP3** (extreme high quality), **M4A/AAC**, **WAV** (lossless uncompressed PCM), and **OPUS**.
- **Interactive Audio Menu**: Select formats and bitrates (320k, 256k, 192k, 128k, VBR, custom) directly from a guided wizard.
- **TikTok Engine**: Downloads videos without watermarks, and turns photo carousels into HD video slideshows with background audio.
- **Browser Cookies**: Access private, login-protected, or age-gated media via `--browser chromium` (or `brave`, `chrome`, `firefox`).
- **Webpage Scraper**: Automatically finds and extracts embedded video streams on arbitrary websites and blogs.
- **Direct Streaming & Resumes**: Resumable HTTP/HTTPS file downloads with `Range: bytes=` support.
- **Real-Time Speed & ETA**: Terminal progress bar displaying speed in **MB/s** (and Mbps) with dynamic countdown.

---

## Prerequisites

- **Python**: 3.10 or higher
- **FFmpeg**: Required for audio/video merging and format conversion
- **aria2** *(optional)*: Recommended for BitTorrent & Magnet P2P swarm downloads

```bash
# Windows (via winget)
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install Gyan.Breeze.aria2

# Arch Linux
sudo pacman -S ffmpeg python aria2

# Ubuntu / Debian
sudo apt install ffmpeg python3 python3-venv aria2
```

---

## Installation

### Linux / macOS
```bash
git clone git@github.com:dularacharith/vdown.git
cd vdown
./install.sh
```
This sets up a virtual environment and links `vdown` into `~/.local/bin/vdown`.

### Windows (CMD or PowerShell)
```cmd
git clone git@github.com:dularacharith/vdown.git
cd vdown
install.bat
```
After running `install.bat`, you can run `.\vdown.bat` directly or add `.venv\Scripts` to your system PATH.

---

## Usage

### 1. Interactive Mode & ASCII Art Hub
Run `vdown` without arguments for the interactive welcome hub and menu:
```bash
vdown
```
Displays a stylized ASCII art banner, system diagnostics (FFmpeg, aria2c, storage space), and interactive options:
- `[1] 🚀 Turbo Download`: Multi-connection accelerated download for direct files (IDM-style)
- `[2] 🧲 Torrent & Magnet`: Unthrottled peer-to-peer BitTorrent swarm downloader
- `[3] 🎬 Video & Stream`: YouTube (playlists & singles), TikTok, Instagram, Facebook, and arbitrary sites
- `[4] 🎵 Music & Audio`: Spotify tracks/playlists, lossless FLAC, 320k MP3, and WAV with cover art
- `[5] 📁 Batch Download`: Download URLs line-by-line from a text file
- `[6] ℹ️ Media Inspector`: Inspect streams and formats without downloading
- `[7] ⚙️ System Diagnostics`: Real-time tool statuses and storage inspection
- `[8] 🚪 Exit`: Clean goodbye

### 2. IDM-Style Turbo Accelerator (Multi-Connection)
Accelerate direct file downloads by splitting them into concurrent byte-range segments to bypass single-thread ISP/server bandwidth throttling:
```bash
# Download direct file using 16 parallel connections (default)
vdown "https://example.com/largefile.zip" --turbo

# Download direct file with 32 concurrent connections
vdown "https://example.com/largefile.zip" --turbo -c 32
```

### 3. BitTorrent & Magnet Downloads (P2P High-Speed)
Download torrents and magnet links with full peer-to-peer swarm speed:
```bash
# Download from magnet link
vdown "magnet:?xt=urn:btih:3b5f903820fae4123&dn=Ubuntu.iso..."

# Download from a .torrent file
vdown "Ubuntu-24.04-Desktop.torrent"
```

### 4. Download YouTube Playlists
```bash
# Download entire playlist into an organized folder
vdown "https://www.youtube.com/playlist?list=PL..."

# Download specific items from playlist (e.g. items 1 to 10)
vdown "https://www.youtube.com/playlist?list=PL..." --playlist-items 1-10

# Download only the single video from a link containing &list=...
vdown "https://www.youtube.com/watch?v=...&list=..." --no-playlist
```

### 5. Extract Audio (Lossless FLAC & 320 kbps MP3)
```bash
# Extract 320 kbps MP3 (default audio bitrate is 320 kbps)
vdown "https://www.youtube.com/watch?v=..." -a

# Extract bit-perfect lossless FLAC audio
vdown "https://www.youtube.com/watch?v=..." -a --audio-format flac

# Extract whole playlist as lossless FLAC tracks
vdown "https://www.youtube.com/playlist?list=PL..." -a --audio-format flac

# Choose custom MP3 bitrate (e.g. 256k or 192k)
vdown "https://www.youtube.com/watch?v=..." -a -aq 256
```

### 6. Spotify Tracks, Playlists & Albums (FLAC, WAV, 320k MP3)
All audio downloads include high-resolution embedded album splash art across **all formats** (WAV, FLAC, MP3, M4A, OPUS), plus a folder `cover.jpg` for playlists.

```bash
# Download Spotify track as high quality 320 kbps MP3 (default) with embedded cover art
vdown "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"

# Download Spotify track as bit-perfect lossless FLAC with embedded album art
vdown "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT" --audio-format flac

# Download Spotify track as uncompressed lossless WAV with embedded ID3v2 APIC splash art
vdown "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT" --audio-format wav

# Download full Spotify playlist / album into organized directory with track numbers & cover.jpg
vdown "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

# Download specific items from Spotify playlist as lossless FLAC
vdown "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" --playlist-items 1-5 --audio-format flac
```

### 7. Choose Video Resolution (e.g. 4K, 1080p, or 720p)
```bash
vdown "https://www.youtube.com/watch?v=..." -q 1080p
```

### 8. TikTok (No Watermark & Photo Slideshows)
```bash
vdown "https://vt.tiktok.com/ZSqF9Tr6a/"

# Extract TikTok soundtrack as lossless FLAC
vdown "https://vt.tiktok.com/ZSqF9Tr6a/" -a --audio-format flac
```

### 9. Instagram & Facebook (With Browser Session)
```bash
vdown "https://www.instagram.com/reel/.../" --browser chromium
vdown "https://www.facebook.com/reel/..." --browser chromium
```

### 10. Inspect Link Details & Available Formats
```bash
vdown "https://..." --info
```

### 11. Custom Output Directory & File Name
```bash
vdown "https://..." -o "video.mp4" -d ~/Downloads
```

### 12. Batch Download
```bash
vdown -b links.txt -d ~/Downloads
```

---

## CLI Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `url` | Video, playlist, file URL, or magnet link to download | None |
| `-i`, `--interactive` | Launch interactive welcome hub & menu | Disabled |
| `--turbo` | Enable IDM-style multi-connection parallel segmented downloading | Disabled |
| `-c`, `--connections` | Number of concurrent streams for turbo/torrent downloading | `16` |
| `--torrent` | Download as BitTorrent / Magnet link | Auto |
| `--info` | Inspect media metadata and formats without downloading | Disabled |
| `-q`, `--quality` | Video quality (`best`, `4k`, `1440p`, `1080p`, `720p`, `480p`, `worst`) | `best` |
| `-f`, `--format-id` | Specific stream format code | Auto |
| `-a`, `--audio-only` | Extract audio only | Disabled |
| `--audio-format` | Audio format (`mp3`, `flac`, `m4a`, `wav`, `opus`, `aac`) | `mp3` |
| `-aq`, `--audio-quality` | Audio bitrate in kbps (`320`, `256`, `192`, `128`, `0`) | `320` |
| `--playlist` | Download full playlist if URL points to one | Auto |
| `--no-playlist` | Download only the single video if URL has video and playlist | Disabled |
| `--playlist-items` | Indices/range of playlist items to download (e.g. `1-5`, `1,3,5`) | All |
| `--format` | Container format (`mp4`, `mkv`, `webm`) | `mp4` |
| `-o`, `--output` | Custom destination filename | Auto |
| `-d`, `--dir` | Output directory path | `downloads` |
| `-b`, `--batch` | Text file containing list of URLs to download | None |
| `--browser` | Extract cookies from browser (`chromium`, `brave`, `chrome`, `firefox`) | None |
| `--cookies` | Path to Netscape-format cookies file | None |
| `--proxy` | HTTP/HTTPS/SOCKS5 proxy URL | None |
| `--rate-limit` | Speed limit cap (e.g. `5M`, `500K`) | Unlimited |

---

## Testing

Run unit and integration tests:

```bash
.venv/bin/python -m unittest discover tests
```
