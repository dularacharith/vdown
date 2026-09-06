# vdown

A fast, versatile command-line video and media downloader. Download videos, audio, streams, and direct media files from virtually any link on the web.

## Features

- **Universal Link Support**: Downloads from YouTube, Facebook, Instagram, TikTok (without watermark), Twitter/X, Vimeo, Reddit, Twitch, and 1800+ other platforms.
- **TikTok Engine**: Downloads videos without watermarks, and turns photo carousels into HD video slideshows with background audio.
- **Browser Cookies**: Access private, login-protected, or age-gated media via `--browser chromium` (or `brave`, `chrome`, `firefox`).
- **Webpage Scraper**: Automatically finds and extracts embedded video streams on arbitrary websites and blogs.
- **Direct Streaming & Resumes**: Resumable HTTP/HTTPS file downloads with `Range: bytes=` support.
- **Real-Time Speed & ETA**: Terminal progress bar displaying speed in **MB/s** (and Mbps) with dynamic countdown.
- **Audio Extraction**: Save audio directly as MP3, M4A, FLAC, or WAV.

---

## Prerequisites

- **Python**: 3.10 or higher
- **FFmpeg**: Required for audio/video merging and format conversion

```bash
# Arch Linux
sudo pacman -S ffmpeg python

# Ubuntu / Debian
sudo apt install ffmpeg python3 python3-venv
```

---

## Installation

Clone the repository and run the installer script:

```bash
git clone git@github.com:dularacharith/vdown.git
cd vdown
./install.sh
```

The installer sets up a virtual environment and symlinks `vdown` to `~/.local/bin/vdown` so you can use it from anywhere in your terminal.

---

## Usage

### 1. Interactive Mode
Run `vdown` without arguments for a guided wizard:
```bash
vdown
```

### 2. Download Best Quality Video
```bash
vdown "https://www.youtube.com/watch?v=..."
```

### 3. Choose Resolution (e.g. 1080p or 720p)
```bash
vdown "https://www.youtube.com/watch?v=..." -q 1080p
```

### 4. Extract Audio (MP3)
```bash
vdown "https://www.youtube.com/watch?v=..." -a
```

### 5. TikTok (No Watermark & Photo Slideshows)
```bash
vdown "https://vt.tiktok.com/ZSqF9Tr6a/"
```

### 6. Instagram & Facebook (With Browser Session)
```bash
vdown "https://www.instagram.com/reel/.../" --browser chromium
vdown "https://www.facebook.com/reel/..." --browser chromium
```

### 7. Inspect Link Details & Available Formats
```bash
vdown "https://..." --info
```

### 8. Custom Output Directory & File Name
```bash
vdown "https://..." -o "video.mp4" -d ~/Downloads
```

### 9. Batch Download
```bash
vdown -b links.txt -d ~/Downloads
```

---

## CLI Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `url` | Video or media URL to download | None |
| `-i`, `--interactive` | Launch interactive wizard | Disabled |
| `--info` | Inspect media metadata and formats without downloading | Disabled |
| `-q`, `--quality` | Video quality (`best`, `4k`, `1440p`, `1080p`, `720p`, `480p`, `worst`) | `best` |
| `-f`, `--format-id` | Specific stream format code | Auto |
| `-a`, `--audio-only` | Extract audio only | Disabled |
| `--audio-format` | Audio codec (`mp3`, `m4a`, `flac`, `wav`, `opus`) | `mp3` |
| `--format` | Container format (`mp4`, `mkv`, `webm`) | `mp4` |
| `-o`, `--output` | Custom destination filename | Auto |
| `-d`, `--dir` | Output directory path | Current dir |
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
