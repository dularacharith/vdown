"""Command Line Interface for Simple Downloader."""

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from simple_downloader import __version__
from simple_downloader.engine import DownloadEngine
from simple_downloader.info import display_media_info, display_formats_table
from simple_downloader.utils import parse_speed_limit, format_bytes
from simple_downloader.turbo import TurboDownloader
from simple_downloader.torrent import TorrentDownloader, is_torrent_or_magnet
from simple_downloader.installer import ensure_tool_installed, is_tool_installed

console = Console()


def create_parser() -> argparse.ArgumentParser:
    """Create command line arguments parser."""
    parser = argparse.ArgumentParser(
        prog="vdown",
        description="🚀 Simple Downloader - Download videos, audio, and streams from any link (YouTube, Facebook, Instagram, TikTok, direct MP4, etc.).",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Video or media URL to download (e.g. YouTube, Facebook, Instagram, TikTok, direct MP4)",
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive guided mode",
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Inspect media information and available formats without downloading",
    )

    parser.add_argument(
        "-q", "--quality",
        default="best",
        help="Video quality: best, 4k, 1440p, 1080p, 720p, 480p, 360p, worst (default: best)",
    )

    parser.add_argument(
        "-f", "--format-id",
        dest="format_id",
        help="Specific format code or combination (e.g. 137+140, 22)",
    )

    parser.add_argument(
        "-a", "--audio-only",
        action="store_true",
        help="Extract audio stream only",
    )

    parser.add_argument(
        "--audio-format",
        default="mp3",
        choices=["mp3", "flac", "m4a", "wav", "opus", "aac"],
        help="Audio format when extracting audio: mp3, flac, m4a, wav, opus, aac (default: mp3)",
    )

    parser.add_argument(
        "-aq", "--audio-quality",
        dest="audio_quality",
        default="320",
        choices=["320", "256", "192", "128", "0"],
        help="Audio quality bitrate in kbps: 320, 256, 192, 128, or 0 (best VBR) (default: 320)",
    )

    parser.add_argument(
        "--format",
        dest="video_format",
        choices=["mp4", "mkv", "webm"],
        help="Preferred video container format (default: mp4)",
    )

    parser.add_argument(
        "-o", "--output",
        help="Custom output filename",
    )

    parser.add_argument(
        "-d", "--dir",
        dest="output_dir",
        default="downloads",
        help="Output destination directory (default: downloads)",
    )

    parser.add_argument(
        "-b", "--batch",
        help="File containing a list of URLs to download (one per line)",
    )

    parser.add_argument(
        "--browser", "--cookies-from-browser",
        dest="browser",
        choices=["chromium", "brave", "chrome", "firefox", "edge", "opera", "vivaldi", "safari"],
        help="Extract session cookies from browser for login-protected sites (Instagram, Facebook, YouTube)",
    )

    parser.add_argument(
        "--cookies",
        dest="cookie_file",
        help="Path to cookies file (Netscape format)",
    )

    parser.add_argument(
        "--proxy",
        help="Use HTTP/HTTPS/SOCKS5 proxy (e.g. socks5://127.0.0.1:1080)",
    )

    parser.add_argument(
        "--user-agent",
        help="Custom User-Agent header string",
    )

    parser.add_argument(
        "--referer",
        help="Custom HTTP Referer header",
    )

    parser.add_argument(
        "--rate-limit",
        help="Maximum download speed (e.g. 5M, 500K, 1G)",
    )

    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Download subtitle file",
    )

    parser.add_argument(
        "--sub-lang",
        default="en",
        help="Subtitle language code (default: en)",
    )

    parser.add_argument(
        "--embed-subs",
        action="store_true",
        help="Embed subtitles into video container",
    )

    parser.add_argument(
        "--embed-thumbnail",
        action="store_true",
        help="Embed thumbnail image into media file",
    )

    parser.add_argument(
        "--embed-metadata",
        action="store_true",
        help="Embed title, artist, and metadata tags",
    )

    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Download full playlist if URL points to one",
    )

    parser.add_argument(
        "--no-playlist",
        action="store_true",
        help="Download only the single video if URL refers to both video and playlist",
    )

    parser.add_argument(
        "--playlist-items",
        help="Indices of playlist items to download (e.g. 1-5, 1,3,5)",
    )

    parser.add_argument(
        "--turbo",
        action="store_true",
        help="Enable IDM-style multi-connection parallel segmented downloading",
    )

    parser.add_argument(
        "-c", "--connections",
        type=int,
        default=16,
        help="Number of concurrent connections for turbo/torrent downloading (default: 16)",
    )

    parser.add_argument(
        "--torrent",
        action="store_true",
        help="Download as BitTorrent / Magnet link using P2P engine",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"vdown {__version__}",
    )

    return parser


def run_interactive_mode(engine: DownloadEngine, initial_url: Optional[str] = None) -> int:
    """Run friendly interactive download wizard."""
    try:
        return _run_interactive_mode_impl(engine, initial_url)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
        return 130


ASCII_BANNER = r"""[bold bright_cyan]
 ██╗   ██╗██████╗  ██████╗ ██╗    ██╗███╗   ██╗
 ██║   ██║██╔══██╗██╔═══██╗██║    ██║████╗  ██║
 ██║   ██║██║  ██║██║   ██║██║ █╗ ██║██╔██╗ ██║
 ╚██╗ ██╔╝██║  ██║██║   ██║██║███╗██║██║╚██╗██║
  ╚████╔╝ ██████╔╝╚██████╔╝╚███╔███╔╝██║ ╚████║
   ╚═══╝  ╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═══╝[/bold bright_cyan]"""


def display_welcome_screen():
    """Display ASCII banner and brief intro overview."""
    console.print(ASCII_BANNER)
    intro_markup = (
        f"[bold white]vdown v{__version__}[/bold white] — [dim]All-in-One CLI Media & High-Speed File Downloader[/dim]\n\n"
        f"• [bold cyan]🚀 Turbo Multi-Stream:[/bold cyan] IDM-style parallel segmented downloading to bypass bandwidth throttle\n"
        f"• [bold magenta]🧲 P2P Torrents & Magnets:[/bold magenta] Unthrottled BitTorrent peer-to-peer swarms\n"
        f"• [bold blue]🎬 Video & Streams:[/bold blue] YouTube (playlists & singles), TikTok (watermark-free), Instagram, Facebook\n"
        f"• [bold green]🎵 Studio Audio Quality:[/bold green] FLAC Lossless, 320 kbps MP3, WAV with embedded splash art (Spotify, TIDAL & Apple Music)\n"
        f"• [dim]Default Output Folder: [underline]{os.path.abspath('downloads')}[/underline][/dim]"
    )
    console.print(
        Panel(
            intro_markup,
            title="[bold yellow]⚡ Welcome to vdown[/bold yellow]",
            border_style="bright_blue",
        )
    )


def display_system_diagnostics():
    """Display diagnostics of installed tools, storage, and system environment."""
    table = Table(title="⚙️ System Diagnostics & Tool Status", show_header=True)
    table.add_column("Component", style="bold cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    # FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        table.add_row("FFmpeg", "[green]Installed[/green]", ffmpeg_path)
    else:
        table.add_row("FFmpeg", "[red]Missing[/red]", "Required for audio conversion & merging")

    # aria2c
    aria2_path = shutil.which("aria2c")
    if aria2_path:
        table.add_row("aria2c (P2P Engine)", "[green]Installed[/green]", aria2_path)
    else:
        table.add_row("aria2c (P2P Engine)", "[yellow]Not Installed[/yellow]", "Install for BitTorrent P2P downloads")

    # Python & OS
    table.add_row("Python", f"[green]{platform.python_version()}[/green]", sys.executable)
    table.add_row("Platform", f"[cyan]{platform.system()} {platform.release()}[/cyan]", platform.machine())

    # Download directory & storage
    down_dir = Path("downloads").resolve()
    down_dir.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(down_dir)
        free_space = format_bytes(usage.free)
        total_space = format_bytes(usage.total)
        table.add_row("Storage", f"[green]{free_space} Free[/green]", f"of {total_space} total ({down_dir})")
    except Exception:
        table.add_row("Storage", "[cyan]Available[/cyan]", str(down_dir))

    console.print(table)

    # Check for missing tools and offer automated installation
    missing_tools = []
    if not is_tool_installed("ffmpeg"):
        missing_tools.append(("ffmpeg", "FFmpeg"))
    if not is_tool_installed("aria2c"):
        missing_tools.append(("aria2c", "aria2c"))

    is_tty = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
    if missing_tools and is_tty:
        missing_names = ", ".join([name for _, name in missing_tools])
        console.print(f"\n[bold yellow]⚡ Missing optional/recommended tools:[/bold yellow] [bold cyan]{missing_names}[/bold cyan]")
        if Confirm.ask("Would you like to install missing tools automatically now?", default=True):
            installed_any = False
            for tool_key, _ in missing_tools:
                if ensure_tool_installed(tool_key, console=console):
                    installed_any = True
            if installed_any:
                display_system_diagnostics()
                return

    Prompt.ask("\n[dim]Press Enter to return to main menu...[/dim]", default="")


def _run_interactive_mode_impl(engine: DownloadEngine, initial_url: Optional[str] = None) -> int:
    """Implementation of interactive download wizard."""
    if initial_url:
        target = initial_url.strip().strip("'\"")
        if is_torrent_or_magnet(target):
            if not ensure_tool_installed("aria2c", purpose="download torrents and magnet links at peer-to-peer speeds", console=console):
                return 1
            torrent_dl = TorrentDownloader(console)
            return torrent_dl.download(target)
        return _run_media_wizard(engine, target)

    display_welcome_screen()

    while True:
        console.print("\n[bold yellow]What would you like to download?[/bold yellow]")
        console.print("  [1] 🚀 [bold cyan]Turbo Download[/bold cyan] (IDM-style Multi-Connection File Accelerator)")
        console.print("  [2] 🧲 [bold magenta]Torrent & Magnet[/bold magenta] (P2P High-Speed Swarm Downloader)")
        console.print("  [3] 🎬 [bold blue]Video & Stream[/bold blue] (YouTube, TikTok, Reels, Facebook, Web)")
        console.print("  [4] 🎵 [bold green]Music & Audio[/bold green] (Spotify, TIDAL, Apple Music, FLAC Lossless, 320k MP3, WAV)")
        console.print("  [5] 📁 [bold white]Batch Download[/bold white] (Download links from a text file)")
        console.print("  [6] ℹ️ [bold yellow]Media Inspector[/bold yellow] (Inspect link formats and quality)")
        console.print("  [7] ⚙️ [bold dim]System Diagnostics[/bold dim] (Check FFmpeg, aria2c, disk space)")
        console.print("  [8] 🚪 [bold red]Exit[/bold red]")

        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="1")

        if choice == "8":
            console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
            return 0

        elif choice == "1":
            link = Prompt.ask("\n[bold yellow]Paste direct download link (e.g. zip, iso, mp4, tar, installer)[/bold yellow]")
            link = link.strip().strip("'\"")
            if not link:
                continue
            conn_str = Prompt.ask("Parallel connections (IDM threads: 4-32)", default="16")
            try:
                conns = int(conn_str)
            except ValueError:
                conns = 16
            out_dir = Prompt.ask("Destination directory", default="downloads")
            turbo = TurboDownloader(connections=conns)
            try:
                turbo.download(link, output_dir=out_dir, connections=conns, console=console)
            except Exception as e:
                console.print(f"[bold red]Download error:[/bold red] {e}")
            return 0

        elif choice == "2":
            # Validate aria2c BEFORE asking for the magnet link / torrent file!
            if not ensure_tool_installed(
                "aria2c",
                purpose="download torrents and magnet links at unthrottled peer-to-peer speeds",
                console=console,
            ):
                continue
            target = Prompt.ask("\n[bold yellow]Paste magnet link (magnet:?...) or path to .torrent file[/bold yellow]")
            target = target.strip().strip("'\"")
            if not target:
                continue
            out_dir = Prompt.ask("Destination directory", default="downloads")
            torrent_dl = TorrentDownloader(console)
            return torrent_dl.download(target, output_dir=out_dir)

        elif choice == "3":
            if not ensure_tool_installed(
                "ffmpeg",
                purpose="download, merge, and convert video streams",
                console=console,
            ):
                continue
            url = Prompt.ask("\n[bold yellow]Paste video or stream link (YouTube, TikTok, IG, FB, Web)[/bold yellow]")
            url = url.strip().strip("'\"")
            if not url:
                continue
            return _run_media_wizard(engine, url, force_audio=False)

        elif choice == "4":
            if not ensure_tool_installed(
                "ffmpeg",
                purpose="extract and convert studio-quality audio (FLAC, MP3, WAV)",
                console=console,
            ):
                continue
            url = Prompt.ask("\n[bold yellow]Paste song, album, playlist or video link (Spotify, TIDAL, Apple Music, YouTube, etc.)[/bold yellow]")
            url = url.strip().strip("'\"")
            if not url:
                continue
            return _run_media_wizard(engine, url, force_audio=True)

        elif choice == "5":
            batch_path = Prompt.ask("\n[bold yellow]Enter path to text file containing URLs[/bold yellow]", default="links.txt")
            batch_path = batch_path.strip().strip("'\"")
            if not batch_path:
                continue
            parser = create_parser()
            args = parser.parse_args(["-b", batch_path])
            return process_batch_file(batch_path, engine, args)

        elif choice == "6":
            url = Prompt.ask("\n[bold yellow]Paste media link to inspect[/bold yellow]")
            url = url.strip().strip("'\"")
            if not url:
                continue
            try:
                with console.status("[cyan]Fetching media info...[/cyan]"):
                    info = engine.get_media_info(url)
                display_media_info(info, console)
                formats = engine.list_formats(info)
                display_formats_table(formats, console)
            except Exception as e:
                console.print(f"[bold red]Failed to inspect URL:[/bold red] {e}")
            return 0

        elif choice == "7":
            display_system_diagnostics()
            continue


def _run_media_wizard(engine: DownloadEngine, url: str, force_audio: bool = False) -> int:
    """Run media inspection and format selection wizard for a given URL."""

    browser = None
    # For social platforms that frequently require cookies (Instagram, Facebook)
    is_social = any(domain in url.lower() for domain in ["instagram.com", "facebook.com", "fb.watch"])
    if is_social:
        console.print("[dim]Note: Instagram & Facebook often require cookies for private videos/reels.[/dim]")
        if Confirm.ask("Use cookies from an installed browser?", default=False):
            browser = Prompt.ask(
                "Select browser",
                choices=["chromium", "brave", "chrome", "firefox", "edge", "opera"],
                default="chromium",
            )

    with console.status("[cyan]Analyzing media link...[/cyan]"):
        try:
            info = engine.get_media_info(url, browser=browser)
        except Exception as e:
            console.print(f"[bold red]Failed to analyze URL:[/bold red] {e}")
            return 1

    display_media_info(info, console)

    # Detect playlist presence in link
    is_sp = info.get("is_spotify", False)
    is_tidal = info.get("is_tidal", False)
    is_apple = info.get("is_apple_music", False)
    is_playlist = info.get("is_playlist", False) or ("list=" in url.lower())
    playlist = False
    playlist_items = None

    if is_playlist:
        entry_count = info.get("playlist_count") or len(info.get("entries") or [])
        item_word = "tracks" if (is_sp or is_tidal or is_apple) else "videos"
        count_str = f" ({entry_count} {item_word})" if entry_count else ""
        if is_apple:
            platform_name = "Apple Music"
        elif is_tidal:
            platform_name = "TIDAL"
        elif is_sp:
            platform_name = "Spotify"
        else:
            platform_name = "YouTube"
        console.print(f"\n[bold yellow]📂 {platform_name} Collection Detected{count_str}[/bold yellow]")
        console.print("  [1] 📥 Download Entire Collection [Default]")
        console.print("  [2] 🔢 Download Specific Range / Items (e.g. 1-10, 1,3,5)")
        if not (is_sp or is_tidal or is_apple):
            console.print("  [3] 🎬 Download Single Video Only")
            pl_choice = Prompt.ask("Playlist Selection", choices=["1", "2", "3"], default="1")
        else:
            console.print("  [3] ❌ Exit")
            pl_choice = Prompt.ask("Playlist Selection", choices=["1", "2", "3"], default="1")
            if pl_choice == "3":
                console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
                return 0

        if pl_choice == "1":
            playlist = True
        elif pl_choice == "2":
            playlist = True
            playlist_items = Prompt.ask(
                "Enter item range to download (e.g. 1-10, 1,3,5, 1-end)",
                default="1-5",
            )
        elif pl_choice == "3":
            playlist = False

    if is_sp or is_tidal or is_apple or force_audio:
        choice = "3"
    else:
        console.print("\n[bold yellow]What would you like to do?[/bold yellow]")
        console.print("  [1] 🌟 Best Quality Video (Video + Audio)")
        console.print("  [2] 🎯 Choose Specific Resolution / Quality")
        console.print("  [3] 🎵 Audio Only (MP3, FLAC Lossless, M4A, WAV, etc.)")
        if not is_playlist:
            console.print("  [4] 📋 List All Available Formats")
            console.print("  [5] ❌ Exit")
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="1")
        else:
            console.print("  [4] ❌ Exit")
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="1")
            if choice == "4":
                choice = "5"

    if choice == "5":
        console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
        return 0

    if choice == "4" and not is_playlist:
        formats = engine.list_formats(info)
        display_formats_table(formats, console)
        if not Confirm.ask("\nProceed to download a specific format?", default=True):
            return 0
        format_id = Prompt.ask("Enter Format ID to download")
        out_dir = Prompt.ask("Output directory", default="downloads")
        return do_download(
            engine=engine,
            url=url,
            format_id=format_id,
            output_dir=out_dir,
            browser=browser,
        )

    quality = "best"
    format_id = None
    audio_only = False
    audio_format = "mp3"
    audio_quality = "320"

    if choice == "2":
        console.print("\n[bold cyan]Select Resolution:[/bold cyan]")
        console.print("  [1] 4K (2160p)")
        console.print("  [2] 2K / 1440p")
        console.print("  [3] 1080p Full HD")
        console.print("  [4] 720p HD")
        console.print("  [5] 480p SD")
        if not is_playlist:
            console.print("  [6] View full raw format table")
            q_choice = Prompt.ask("Choice", choices=["1", "2", "3", "4", "5", "6"], default="3")
        else:
            q_choice = Prompt.ask("Choice", choices=["1", "2", "3", "4", "5"], default="3")
        q_map = {"1": "4k", "2": "1440p", "3": "1080p", "4": "720p", "5": "480p"}
        if q_choice in q_map:
            quality = q_map[q_choice]
        elif q_choice == "6" and not is_playlist:
            formats = engine.list_formats(info)
            display_formats_table(formats, console)
            format_id = Prompt.ask("Enter Format ID to download")

    elif choice == "3":
        audio_only = True
        console.print("\n[bold cyan]Select Audio Format:[/bold cyan]")
        console.print("  [1] 🎵 MP3 (Selectable Bitrate: 320k, 256k, 192k, 128k) [Default]")
        console.print("  [2] 🎼 FLAC Lossless (Studio Quality - Bit-Perfect Lossless)")
        console.print("  [3] 📱 M4A / AAC (High Quality Apple/Mobile Compatible)")
        console.print("  [4] 🎹 WAV (Lossless Uncompressed PCM Audio)")
        console.print("  [5] 🌐 OPUS (Modern High-Efficiency Audio)")

        fmt_choice = Prompt.ask("Audio Format", choices=["1", "2", "3", "4", "5"], default="1")

        if fmt_choice == "1":
            audio_format = "mp3"
            console.print("\n[bold cyan]Select MP3 Bitrate:[/bold cyan]")
            console.print("  [1] 💎 320 kbps (Extreme Quality - Maximum MP3 Bitrate) [Default]")
            console.print("  [2] 🌟 256 kbps (Very High Quality)")
            console.print("  [3] ⚡ 192 kbps (Standard High Quality)")
            console.print("  [4] 📦 128 kbps (Compact File Size)")
            console.print("  [5] 🎛 Best VBR (Variable Bitrate ~245 kbps, V0)")
            console.print("  [6] ✏ Custom Bitrate")
            br_choice = Prompt.ask("Bitrate Choice", choices=["1", "2", "3", "4", "5", "6"], default="1")
            if br_choice == "1":
                audio_quality = "320"
            elif br_choice == "2":
                audio_quality = "256"
            elif br_choice == "3":
                audio_quality = "192"
            elif br_choice == "4":
                audio_quality = "128"
            elif br_choice == "5":
                audio_quality = "0"
            elif br_choice == "6":
                custom_br = Prompt.ask("Enter bitrate in kbps (e.g. 320, 256, 192)", default="320")
                audio_quality = custom_br.rstrip("kK")

        elif fmt_choice == "2":
            audio_format = "flac"
            audio_quality = "0"
            console.print("[bold green]✔ Selected FLAC Lossless (Studio Quality - Bit-Perfect Lossless)[/bold green]")

        elif fmt_choice == "3":
            audio_format = "m4a"
            console.print("\n[bold cyan]Select M4A / AAC Bitrate:[/bold cyan]")
            console.print("  [1] 320 kbps [Default]")
            console.print("  [2] 256 kbps")
            console.print("  [3] 192 kbps")
            console.print("  [4] 128 kbps")
            m_choice = Prompt.ask("Bitrate Choice", choices=["1", "2", "3", "4"], default="1")
            m_map = {"1": "320", "2": "256", "3": "192", "4": "128"}
            audio_quality = m_map[m_choice]

        elif fmt_choice == "4":
            audio_format = "wav"
            audio_quality = "0"
            console.print("[bold green]✔ Selected WAV Uncompressed Lossless PCM[/bold green]")

        elif fmt_choice == "5":
            audio_format = "opus"
            console.print("\n[bold cyan]Select OPUS Bitrate:[/bold cyan]")
            console.print("  [1] 320 kbps [Default]")
            console.print("  [2] 256 kbps")
            console.print("  [3] 160 kbps")
            console.print("  [4] 128 kbps")
            o_choice = Prompt.ask("Bitrate Choice", choices=["1", "2", "3", "4"], default="1")
            o_map = {"1": "320", "2": "256", "3": "160", "4": "128"}
            audio_quality = o_map[o_choice]

    out_dir = Prompt.ask("\nDestination directory", default="downloads")

    return do_download(
        engine=engine,
        url=url,
        quality=quality,
        format_id=format_id,
        audio_only=audio_only,
        audio_format=audio_format,
        audio_quality=audio_quality,
        playlist=playlist,
        playlist_items=playlist_items,
        output_dir=out_dir,
        browser=browser,
    )


def do_download(
    engine: DownloadEngine,
    url: str,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = "downloads",
    quality: str = "best",
    format_id: Optional[str] = None,
    audio_only: bool = False,
    audio_format: str = "mp3",
    audio_quality: str = "320",
    video_format: Optional[str] = None,
    rate_limit: Optional[int] = None,
    subtitles: bool = False,
    sub_lang: str = "en",
    embed_subs: bool = False,
    embed_thumbnail: bool = False,
    embed_metadata: bool = False,
    playlist: bool = False,
    playlist_items: Optional[str] = None,
    browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
) -> int:
    """Execute download and print summary."""
    try:
        target_dir = output_dir or "downloads"
        console.print(f"\n[bold green]Starting download:[/bold green] [underline cyan]{url}[/underline cyan]")
        result = engine.download(
            url=url,
            output_path=output_path,
            output_dir=target_dir,
            quality=quality,
            format_id=format_id,
            audio_only=audio_only,
            audio_format=audio_format,
            audio_quality=audio_quality,
            video_format=video_format,
            rate_limit=rate_limit,
            subtitles=subtitles,
            sub_lang=sub_lang,
            embed_subs=embed_subs,
            embed_thumbnail=embed_thumbnail,
            embed_metadata=embed_metadata,
            playlist=playlist,
            playlist_items=playlist_items,
            browser=browser,
            cookie_file=cookie_file,
            proxy=proxy,
            user_agent=user_agent,
            referer=referer,
        )

        file_desc = f"[bold green]✔ Download Completed Successfully![/bold green]"
        if result and os.path.exists(result):
            if os.path.isdir(result):
                items = [f for f in os.listdir(result) if not f.endswith(".part") and not f.startswith(".")]
                file_desc = f"[bold green]✔ Playlist Download Completed ({len(items)} items)![/bold green]"
                file_desc += f"\n📁 Folder: [bold white]{result}[/bold white]"
            else:
                size_str = format_bytes(os.path.getsize(result))
                file_desc += f"\n📁 [bold white]{result}[/bold white] ({size_str})"

        console.print(
            Panel(
                file_desc,
                border_style="green",
                expand=False,
            )
        )
        return 0
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[bold red]Error during download:[/bold red] {e}")
        return 1


def process_batch_file(filepath: str, engine: DownloadEngine, args: argparse.Namespace) -> int:
    """Process multiple URLs from a text file."""
    path = Path(filepath)
    if not path.exists():
        console.print(f"[bold red]Batch file not found:[/bold red] {filepath}")
        return 1

    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    if not lines:
        console.print("[yellow]Batch file is empty.[/yellow]")
        return 0

    console.print(f"[bold cyan]Found {len(lines)} URLs to download from {filepath}[/bold cyan]\n")
    failed = 0
    success = 0

    rate_limit_val = parse_speed_limit(args.rate_limit)

    try:
        for idx, url in enumerate(lines, 1):
            console.print(f"[bold yellow][{idx}/{len(lines)}][/bold yellow] Processing {url}")
            res = do_download(
                engine=engine,
                url=url,
                output_dir=args.output_dir,
                quality=args.quality,
                format_id=args.format_id,
                audio_only=args.audio_only,
                audio_format=args.audio_format,
                audio_quality=args.audio_quality,
                video_format=args.video_format,
                rate_limit=rate_limit_val,
                subtitles=args.subtitles,
                sub_lang=args.sub_lang,
                embed_subs=args.embed_subs,
                embed_thumbnail=args.embed_thumbnail,
                embed_metadata=args.embed_metadata,
                playlist=args.playlist,
                playlist_items=args.playlist_items,
                browser=args.browser,
                cookie_file=args.cookie_file,
                proxy=args.proxy,
                user_agent=args.user_agent,
                referer=args.referer,
            )
            if res == 0:
                success += 1
            elif res == 130:
                return 130
            else:
                failed += 1

        console.print(f"\n[bold]Batch Summary:[/bold] [green]{success} Succeeded[/green], [red]{failed} Failed[/red]")
        return 0 if failed == 0 else 1
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
        return 130


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    try:
        parser = create_parser()
        args = parser.parse_args(argv)

        engine = DownloadEngine(console_instance=console)

        # If no URL and no batch and interactive flag or just `vdown` with no args:
        if (not args.url and not args.batch) or args.interactive:
            return run_interactive_mode(engine, initial_url=args.url)

        # Batch mode
        if args.batch:
            return process_batch_file(args.batch, engine, args)

        # Single URL inspection mode (--info)
        if args.info:
            try:
                with console.status("[cyan]Fetching media info...[/cyan]"):
                    info = engine.get_media_info(
                        args.url,
                        browser=args.browser,
                        cookie_file=args.cookie_file,
                        proxy=args.proxy,
                        user_agent=args.user_agent,
                        referer=args.referer,
                    )
                display_media_info(info, console)
                formats = engine.list_formats(info)
                display_formats_table(formats, console)
                return 0
            except Exception as e:
                console.print(f"[bold red]Failed to fetch info:[/bold red] {e}")
                return 1

        # BitTorrent / Magnet mode
        if getattr(args, "torrent", False) or is_torrent_or_magnet(args.url):
            torrent_dl = TorrentDownloader(console)
            return torrent_dl.download(
                args.url,
                output_dir=args.output_dir,
                connections=args.connections,
            )

        # Turbo Multi-Connection mode
        if getattr(args, "turbo", False):
            turbo = TurboDownloader(connections=args.connections)
            try:
                res = turbo.download(
                    args.url,
                    output_path=args.output,
                    output_dir=args.output_dir,
                    connections=args.connections,
                    console=console,
                )
                return 0 if res else 1
            except Exception as e:
                console.print(f"[bold red]Turbo download failed:[/bold red] {e}")
                return 1

        # Single URL download mode
        rate_limit_val = parse_speed_limit(args.rate_limit)

        from simple_downloader.spotify import is_spotify_url, parse_spotify_url
        from simple_downloader.tidal import is_tidal_url, parse_tidal_url
        from simple_downloader.applemusic import is_apple_music_url, parse_apple_music_url

        is_spotify = is_spotify_url(args.url) if args.url else False
        is_sp_playlist = False
        if is_spotify:
            parsed_sp = parse_spotify_url(args.url)
            if parsed_sp and parsed_sp[0] in ("playlist", "album"):
                is_sp_playlist = True

        is_tidal = is_tidal_url(args.url) if args.url else False
        is_tidal_collection = False
        if is_tidal:
            parsed_td = parse_tidal_url(args.url)
            if parsed_td and parsed_td[0] in ("playlist", "album"):
                is_tidal_collection = True

        is_apple = is_apple_music_url(args.url) if args.url else False
        is_apple_collection = False
        if is_apple:
            parsed_am = parse_apple_music_url(args.url)
            if parsed_am and parsed_am[0] in ("playlist", "album"):
                is_apple_collection = True

        is_pure_playlist = (
            bool(args.url and ("playlist?list=" in args.url.lower()))
            or is_sp_playlist
            or is_tidal_collection
            or is_apple_collection
        )
        playlist = (args.playlist or is_pure_playlist or bool(args.playlist_items)) and not args.no_playlist
        audio_only = args.audio_only or is_spotify or is_tidal or is_apple

        return do_download(
            engine=engine,
            url=args.url,
            output_path=args.output,
            output_dir=args.output_dir,
            quality=args.quality,
            format_id=args.format_id,
            audio_only=audio_only,
            audio_format=args.audio_format,
            audio_quality=args.audio_quality,
            video_format=args.video_format,
            rate_limit=rate_limit_val,
            subtitles=args.subtitles,
            sub_lang=args.sub_lang,
            embed_subs=args.embed_subs,
            embed_thumbnail=args.embed_thumbnail,
            embed_metadata=args.embed_metadata,
            playlist=playlist,
            playlist_items=args.playlist_items,
            browser=args.browser,
            cookie_file=args.cookie_file,
            proxy=args.proxy,
            user_agent=args.user_agent,
            referer=args.referer,
        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Goodbye![/bold yellow]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
