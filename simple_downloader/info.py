"""Media information presentation and format table formatting."""

from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from simple_downloader.utils import format_bytes, format_duration


def display_media_info(info: Dict[str, Any], console: Console) -> None:
    """Display high-level metadata about the media or playlist."""
    is_playlist = info.get("is_playlist", False)
    title = info.get("title", "Unknown Title")
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "N/A"

    details = Text()
    if is_playlist:
        entries = info.get("entries") or []
        count = info.get("playlist_count") or len(entries)
        details.append("Type: ", style="bold yellow")
        if info.get("is_spotify"):
            s_type = info.get("spotify_type", "playlist").capitalize()
            details.append(f"Spotify {s_type}\n")
            details.append(f"{s_type} Title: ", style="bold cyan")
            details.append(f"{title}\n")
            if uploader and uploader != "N/A":
                details.append("Curator/Artist: ", style="bold cyan")
                details.append(f"{uploader}\n")
            details.append("Total Tracks: ", style="bold cyan")
            details.append(f"{count} tracks\n")
            if entries and len(entries) > 0:
                first_entry = entries[0]
                first_title = first_entry.get("title", "Track 1") if isinstance(first_entry, dict) else "Track 1"
                details.append("First Track: ", style="dim cyan")
                details.append(f"{first_title}\n")
                if len(entries) > 1:
                    last_entry = entries[-1]
                    last_title = last_entry.get("title", f"Track {len(entries)}") if isinstance(last_entry, dict) else f"Track {len(entries)}"
                    details.append("Last Track: ", style="dim cyan")
                    details.append(f"{last_title}\n")
        elif info.get("is_tidal"):
            t_type = info.get("tidal_type", "playlist").capitalize()
            details.append(f"TIDAL {t_type}\n")
            details.append(f"{t_type} Title: ", style="bold cyan")
            details.append(f"{title}\n")
            if info.get("artist"):
                details.append("Artist: ", style="bold cyan")
                details.append(f"{info['artist']}\n")
            details.append("Total Tracks: ", style="bold cyan")
            details.append(f"{count} tracks\n")
            if entries and len(entries) > 0:
                first_entry = entries[0]
                first_title = first_entry.get("title", "Track 1") if isinstance(first_entry, dict) else "Track 1"
                details.append("First Track: ", style="dim cyan")
                details.append(f"{first_title}\n")
                if len(entries) > 1:
                    last_entry = entries[-1]
                    last_title = last_entry.get("title", f"Track {len(entries)}") if isinstance(last_entry, dict) else f"Track {len(entries)}"
                    details.append("Last Track: ", style="dim cyan")
                    details.append(f"{last_title}\n")
        else:
            details.append("YouTube Playlist\n")
            details.append("Playlist Title: ", style="bold cyan")
            details.append(f"{title}\n")
            details.append("Channel/Curator: ", style="bold cyan")
            details.append(f"{uploader}\n")
            details.append("Total Videos: ", style="bold cyan")
            details.append(f"{count} items\n")
            if entries and len(entries) > 0:
                first_entry = entries[0]
                first_title = first_entry.get("title", "Item 1") if isinstance(first_entry, dict) else "Item 1"
                details.append("First Video: ", style="dim cyan")
                details.append(f"{first_title}\n")
                if len(entries) > 1:
                    last_entry = entries[-1]
                    last_title = last_entry.get("title", f"Item {len(entries)}") if isinstance(last_entry, dict) else f"Item {len(entries)}"
                    details.append("Last Video: ", style="dim cyan")
                    details.append(f"{last_title}\n")
    else:
        duration = format_duration(info.get("duration"))
        views = f"{info['view_count']:,}" if info.get("view_count") is not None else "N/A"
        upload_date = info.get("upload_date", "N/A")
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        details.append("Title: ", style="bold cyan")
        details.append(f"{title}\n")
        details.append("Author/Source: ", style="bold cyan")
        details.append(f"{uploader}\n")
        details.append("Duration: ", style="bold cyan")
        details.append(f"{duration}\n")
        if views != "N/A":
            details.append("Views: ", style="bold cyan")
            details.append(f"{views}\n")
        details.append("Upload Date: ", style="bold cyan")
        details.append(f"{upload_date}\n")

        if info.get("is_direct"):
            filesize = format_bytes(info.get("filesize"))
            details.append("Type: ", style="bold green")
            details.append("Direct File / Stream\n")
            details.append("File Size: ", style="bold green")
            details.append(f"{filesize}\n")
        elif info.get("is_tiktok"):
            details.append("Platform: ", style="bold green")
            details.append("TikTok (Watermark-Free Engine)\n")
            if info.get("is_photo"):
                details.append("Post Type: ", style="bold magenta")
                details.append(f"Photo Carousel / Slideshow ({len(info.get('images', []))} slides)\n")
        elif info.get("is_spotify"):
            details.append("Platform: ", style="bold green")
            details.append("Spotify (Lossless / High-Fidelity Audio)\n")
            if info.get("album"):
                details.append("Album: ", style="bold cyan")
                details.append(f"{info['album']}\n")
        elif info.get("is_tidal"):
            details.append("Platform: ", style="bold cyan")
            details.append("TIDAL (Lossless / Master Quality Audio)\n")
            if info.get("artist"):
                details.append("Artist: ", style="bold cyan")
                details.append(f"{info['artist']}\n")
            if info.get("album"):
                details.append("Album: ", style="bold cyan")
                details.append(f"{info['album']}\n")
            if info.get("audio_quality"):
                details.append("Audio Quality: ", style="bold green")
                details.append(f"{info['audio_quality']}\n")

    console.print(
        Panel(
            details,
            title="[bold yellow]Media Details[/bold yellow]" if not is_playlist else "[bold yellow]Playlist Details[/bold yellow]",
            border_style="bright_blue",
            expand=False,
        )
    )


def display_formats_table(formats: List[Dict[str, Any]], console: Console) -> None:
    """Render an organized Rich table showing available video and audio formats."""
    if not formats:
        console.print("[dim]No format breakdown available (direct or single stream).[/dim]")
        return

    table = Table(title="Available Formats", border_style="cyan", show_lines=False)
    table.add_column("ID", style="bold yellow", justify="right")
    table.add_column("Ext", style="green")
    table.add_column("Resolution", style="bold white")
    table.add_column("FPS", justify="right")
    table.add_column("Video Codec", style="magenta")
    table.add_column("Audio Codec", style="blue")
    table.add_column("Bitrate", justify="right")
    table.add_column("Size", justify="right", style="cyan")

    # Filter out redundant formats or display cleanly
    for f in formats:
        fid = str(f.get("format_id", ""))
        ext = str(f.get("ext", ""))
        res = str(f.get("resolution", ""))
        fps = str(f.get("fps", "")) if f.get("fps") else "-"
        vcodec = f.get("vcodec") or "-"
        acodec = f.get("acodec") or "-"
        tbr = f"{f['tbr']:.0f}k" if f.get("tbr") else "-"
        size = format_bytes(f.get("filesize"))

        table.add_row(fid, ext, res, fps, vcodec, acodec, tbr, size)

    console.print(table)
