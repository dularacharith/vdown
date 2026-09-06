"""Custom Rich progress bar components with dual MB/s and Mbps speed display."""

from typing import Optional
from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
)
from rich.text import Text


class DualSpeedColumn(ProgressColumn):
    """Renders download speed with precise MB/s and corresponding Mbps."""

    def render(self, task) -> Text:
        speed = task.fields.get("speed")
        if speed is None:
            speed = task.speed
        if speed is None or speed <= 0:
            return Text("Calculating speed...", style="dim")

        # Bytes per second to Megabytes per second and Megabits per second
        mb_per_sec = speed / (1024 * 1024)
        mbps = (speed * 8) / 1_000_000  # Standard network Mbps (decimal bits)

        if mb_per_sec >= 1.0:
            speed_str = f"{mb_per_sec:.2f} MB/s"
        elif speed >= 1024:
            speed_str = f"{speed / 1024:.1f} KB/s"
        else:
            speed_str = f"{speed:.0f} B/s"

        return Text.assemble(
            ("⚡ ", "bold yellow"),
            (speed_str, "bold green"),
            (f" ({mbps:.1f} Mbps)", "cyan"),
        )


class DynamicETAColumn(ProgressColumn):
    """Renders formatted ETA from task fields or calculated remaining time."""

    def render(self, task) -> Text:
        eta = task.fields.get("eta")
        if eta is None:
            eta = task.time_remaining
        if eta is None or eta < 0:
            return Text("ETA: --:--", style="dim")

        secs = int(eta)
        mins = secs // 60
        secs = secs % 60
        hours = mins // 60
        mins = mins % 60

        if hours > 0:
            eta_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
        else:
            eta_str = f"{mins:02d}:{secs:02d}"

        return Text.assemble(
            ("⏳ ETA: ", "dim white"),
            (eta_str, "bold cyan"),
        )


def create_download_progress(show_progress: bool = True) -> Progress:
    """Create a unified, informative progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        BarColumn(bar_width=30),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        DualSpeedColumn(),
        "•",
        DynamicETAColumn(),
        disable=not show_progress,
    )
