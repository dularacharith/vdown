"""Media information presentation and format table formatting."""

from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from simple_downloader.utils import format_bytes, format_duration


def display_media_info(info: Dict[str, Any], console: Console) -> None:
    """Display high-level metadata about the media."""
    title = info.get("title", "Unknown Title")
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "N/A"
    duration = format_duration(info.get("duration"))
    views = f"{info['view_count']:,}" if info.get("view_count") is not None else "N/A"
    upload_date = info.get("upload_date", "N/A")
    if upload_date and len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

    details = Text()
    details.append("Title: ", style="bold cyan")
    details.append(f"{title}\n")
    details.append("Author/Source: ", style="bold cyan")
    details.append(f"{uploader}\n")
    details.append("Duration: ", style="bold cyan")
    details.append(f"{duration}\n")
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

    console.print(
        Panel(
            details,
            title="[bold yellow]Media Details[/bold yellow]",
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
