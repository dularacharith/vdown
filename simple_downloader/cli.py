"""Command Line Interface for Simple Downloader."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text

from simple_downloader import __version__
from simple_downloader.engine import DownloadEngine
from simple_downloader.info import display_media_info, display_formats_table
from simple_downloader.utils import parse_speed_limit, format_bytes

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
        choices=["mp3", "m4a", "flac", "wav", "opus", "aac"],
        help="Audio format when extracting audio (default: mp3)",
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
        default=".",
        help="Output destination directory (default: current directory)",
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
        "--playlist-items",
        help="Indices of playlist items to download (e.g. 1-5, 1,3,5)",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"vdown {__version__}",
    )

    return parser


def run_interactive_mode(engine: DownloadEngine, initial_url: Optional[str] = None):
    """Run friendly interactive download wizard."""
    console.print(
        Panel(
            Text(
                f"🎬 Simple Downloader v{__version__}\n"
                "Universal CLI Video & Media Downloader\n"
                "Supports YouTube, Facebook, Instagram, TikTok, X/Twitter, and Any Link",
                justify="center",
                style="bold bright_cyan",
            ),
            border_style="bright_blue",
        )
    )

    url = initial_url
    if not url:
        url = Prompt.ask("\n[bold yellow]Paste the video or media link[/bold yellow]")
        url = url.strip().strip("'\"")

    if not url:
        console.print("[red]No URL provided. Exiting.[/red]")
        return 1

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

    console.print("\n[bold yellow]What would you like to do?[/bold yellow]")
    console.print("  [1] 🌟 Best Quality Video (Video + Audio)")
    console.print("  [2] 🎯 Choose Specific Resolution / Quality")
    console.print("  [3] 🎵 Audio Only (MP3)")
    console.print("  [4] 📋 List All Available Formats")
    console.print("  [5] ❌ Exit")

    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="1")

    if choice == "5":
        console.print("[dim]Aborted.[/dim]")
        return 0

    if choice == "4":
        formats = engine.list_formats(info)
        display_formats_table(formats, console)
        if not Confirm.ask("\nProceed to download a specific format?", default=True):
            return 0
        format_id = Prompt.ask("Enter Format ID to download")
        out_dir = Prompt.ask("Output directory", default=".")
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

    if choice == "2":
        console.print("\n[bold cyan]Select Resolution:[/bold cyan]")
        console.print("  [1] 4K (2160p)")
        console.print("  [2] 2K / 1440p")
        console.print("  [3] 1080p Full HD")
        console.print("  [4] 720p HD")
        console.print("  [5] 480p SD")
        console.print("  [6] View full raw format table")
        q_choice = Prompt.ask("Choice", choices=["1", "2", "3", "4", "5", "6"], default="3")
        q_map = {"1": "4k", "2": "1440p", "3": "1080p", "4": "720p", "5": "480p"}
        if q_choice in q_map:
            quality = q_map[q_choice]
        else:
            formats = engine.list_formats(info)
            display_formats_table(formats, console)
            format_id = Prompt.ask("Enter Format ID to download")

    elif choice == "3":
        audio_only = True

    out_dir = Prompt.ask("\nDestination directory", default=".")

    return do_download(
        engine=engine,
        url=url,
        quality=quality,
        format_id=format_id,
        audio_only=audio_only,
        output_dir=out_dir,
        browser=browser,
    )


def do_download(
    engine: DownloadEngine,
    url: str,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    quality: str = "best",
    format_id: Optional[str] = None,
    audio_only: bool = False,
    audio_format: str = "mp3",
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
        console.print(f"\n[bold green]Starting download:[/bold green] [underline cyan]{url}[/underline cyan]")
        result = engine.download(
            url=url,
            output_path=output_path,
            output_dir=output_dir,
            quality=quality,
            format_id=format_id,
            audio_only=audio_only,
            audio_format=audio_format,
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
        console.print("\n[yellow]Download interrupted by user.[/yellow]")
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
        else:
            failed += 1

    console.print(f"\n[bold]Batch Summary:[/bold] [green]{success} Succeeded[/green], [red]{failed} Failed[/red]")
    return 0 if failed == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
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

    # Single URL download mode
    rate_limit_val = parse_speed_limit(args.rate_limit)

    return do_download(
        engine=engine,
        url=args.url,
        output_path=args.output,
        output_dir=args.output_dir,
        quality=args.quality,
        format_id=args.format_id,
        audio_only=args.audio_only,
        audio_format=args.audio_format,
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


if __name__ == "__main__":
    sys.exit(main())
