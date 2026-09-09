"""BitTorrent and Magnet download module for simple-downloader.

Provides high-speed peer-to-peer downloading for magnet links and .torrent files,
with pure Python torrent inspection and aria2c P2P acceleration.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

from simple_downloader.utils import format_bytes, sanitize_filename
from simple_downloader.installer import ensure_tool_installed, is_tool_installed, get_install_command_for_tool


def is_torrent_or_magnet(target: str) -> bool:
    """Check whether a target string is a magnet link or .torrent file/URL."""
    if not target:
        return False
    target_clean = target.strip()
    if target_clean.lower().startswith("magnet:?"):
        return True
    if target_clean.lower().endswith(".torrent") or ".torrent?" in target_clean.lower():
        return True
    if os.path.isfile(target_clean) and target_clean.lower().endswith(".torrent"):
        return True
    return False


def decode_bencode(data: bytes, index: int = 0) -> Tuple[Any, int]:
    """Lightweight pure-Python bencode decoder."""
    if index >= len(data):
        raise ValueError("Unexpected end of bencoded data")

    char = data[index : index + 1]

    # Integer: i<digits>e
    if char == b"i":
        end = data.find(b"e", index + 1)
        if end == -1:
            raise ValueError("Unterminated integer in bencode")
        val = int(data[index + 1 : end])
        return val, end + 1

    # List: l<items>e
    elif char == b"l":
        items = []
        curr = index + 1
        while curr < len(data) and data[curr : curr + 1] != b"e":
            item, curr = decode_bencode(data, curr)
            items.append(item)
        return items, curr + 1

    # Dictionary: d<key><value>...e
    elif char == b"d":
        d = {}
        curr = index + 1
        while curr < len(data) and data[curr : curr + 1] != b"e":
            key, curr = decode_bencode(data, curr)
            if isinstance(key, bytes):
                try:
                    key = key.decode("utf-8", errors="replace")
                except Exception:
                    pass
            val, curr = decode_bencode(data, curr)
            d[key] = val
        return d, curr + 1

    # Byte String: <len>:<string>
    elif char.isdigit():
        colon = data.find(b":", index)
        if colon == -1:
            raise ValueError("Invalid string prefix in bencode")
        length = int(data[index:colon])
        start = colon + 1
        end = start + length
        return data[start:end], end

    else:
        raise ValueError(f"Unknown bencode token '{char}' at index {index}")


def parse_torrent_file(file_path: str) -> Dict[str, Any]:
    """Parse a .torrent file to extract metadata without external dependencies."""
    with open(file_path, "rb") as f:
        content = f.read()

    torrent_dict, _ = decode_bencode(content)
    info = torrent_dict.get("info", {})

    # Compute info_hash
    # To get accurate SHA1, find the byte slice of 'info' in the original file
    info_start = content.find(b"4:info")
    info_hash = ""
    if info_start != -1:
        try:
            _, info_end = decode_bencode(content, info_start + 6)
            info_bytes = content[info_start + 6 : info_end]
            info_hash = hashlib.sha1(info_bytes).hexdigest()
        except Exception:
            pass

    name = info.get("name.utf-8") or info.get("name")
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    name = str(name or "Unknown Torrent")

    files = []
    total_size = 0
    if "files" in info:
        for f in info["files"]:
            f_size = f.get("length", 0)
            total_size += f_size
            path_parts = f.get("path.utf-8") or f.get("path", [])
            decoded_parts = [
                p.decode("utf-8", errors="replace") if isinstance(p, bytes) else str(p)
                for p in path_parts
            ]
            files.append({"path": "/".join(decoded_parts), "size": f_size})
    else:
        total_size = info.get("length", 0)
        files.append({"path": name, "size": total_size})

    announce = torrent_dict.get("announce")
    if isinstance(announce, bytes):
        announce = announce.decode("utf-8", errors="replace")

    return {
        "name": name,
        "total_size": total_size,
        "files": files,
        "info_hash": info_hash,
        "announce": announce,
        "comment": torrent_dict.get("comment", b"").decode("utf-8", errors="replace") if isinstance(torrent_dict.get("comment"), bytes) else "",
    }


def parse_magnet_link(magnet: str) -> Dict[str, Any]:
    """Parse magnet link components."""
    parsed = urllib.parse.urlparse(magnet)
    qs = urllib.parse.parse_qs(parsed.query)

    display_name = qs.get("dn", ["Unknown Torrent"])[0]
    xt_list = qs.get("xt", [])
    info_hash = ""
    for xt in xt_list:
        if xt.startswith("urn:btih:"):
            info_hash = xt.replace("urn:btih:", "")
            break

    trackers = qs.get("tr", [])
    return {
        "name": display_name,
        "info_hash": info_hash,
        "trackers": trackers,
        "raw": magnet,
    }


def get_aria2_install_command() -> str:
    """Return platform-specific command to install aria2."""
    system = platform.system().lower()
    if system == "linux":
        if os.path.exists("/etc/arch-release") or os.path.exists("/usr/share/omarchy"):
            return "sudo pacman -S aria2"
        elif os.path.exists("/etc/debian_version"):
            return "sudo apt install aria2"
        elif os.path.exists("/etc/fedora-release"):
            return "sudo dnf install aria2"
        return "sudo pacman -S aria2  # or: sudo apt install aria2"
    elif system == "windows":
        return "winget install Gyan.Breeze.aria2  # or: winget install aria2"
    elif system == "darwin":
        return "brew install aria2"
    return "Install aria2 package for your operating system"


class TorrentDownloader:
    """P2P Torrent and Magnet link downloader using aria2c engine."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def has_aria2c(self) -> bool:
        """Check if aria2c executable is installed and reachable."""
        return is_tool_installed("aria2c")

    def display_missing_aria2_prompt(self) -> bool:
        """Inform the user that aria2c is required for BitTorrent P2P downloads and prompt to install."""
        return ensure_tool_installed(
            "aria2c",
            purpose="download torrents and magnet links at unthrottled peer-to-peer speeds",
            console=self.console,
            interactive=True,
        )

    def download(
        self,
        target: str,
        output_dir: Optional[str] = "downloads",
        connections: int = 16,
    ) -> int:
        """Download a magnet link or .torrent file with unthrottled P2P speed."""
        # Check for aria2c before downloading
        if not self.has_aria2c():
            if not self.display_missing_aria2_prompt():
                return 1

        target_clean = target.strip().strip("'\"")
        dest_dir = Path(output_dir or "downloads").expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Inspect and display torrent metadata if available
        if target_clean.lower().startswith("magnet:?"):
            meta = parse_magnet_link(target_clean)
            self.console.print(
                Panel(
                    f"[bold cyan]Magnet Link:[/bold cyan] [bold white]{meta['name']}[/bold white]\n"
                    f"[dim]Info Hash:[/dim] {meta['info_hash']}\n"
                    f"[dim]Trackers:[/dim] {len(meta['trackers'])} trackers",
                    title="🧲 BitTorrent Magnet",
                    border_style="bright_magenta",
                )
            )
        elif os.path.isfile(target_clean) and target_clean.lower().endswith(".torrent"):
            try:
                t_info = parse_torrent_file(target_clean)
                table = Table(title=f"🧲 Torrent Details: {t_info['name']}", show_header=True)
                table.add_column("File", style="cyan")
                table.add_column("Size", justify="right", style="green")

                for f in t_info["files"][:10]:
                    table.add_row(f["path"], format_bytes(f["size"]))
                if len(t_info["files"]) > 10:
                    table.add_row(f"... and {len(t_info['files']) - 10} more files", "")

                self.console.print(table)
                self.console.print(
                    f"[dim]Total Size:[/dim] [bold green]{format_bytes(t_info['total_size'])}[/bold green] | "
                    f"[dim]Info Hash:[/dim] {t_info['info_hash']}"
                )
            except Exception as e:
                self.console.print(f"[dim]Note: could not parse torrent metadata: {e}[/dim]")

        # Run aria2c
        aria_cmd = [
            "aria2c",
            f"--dir={dest_dir}",
            "--enable-dht=true",
            "--bt-enable-lpd=true",
            "--bt-max-peers=60",
            f"--max-connection-per-server={connections}",
            f"--split={connections}",
            "--seed-time=0",
            "--summary-interval=1",
            target_clean,
        ]

        self.console.print(f"\n[bold cyan]🚀 Starting BitTorrent P2P Swarm Download into:[/bold cyan] [bold white]{dest_dir}[/bold white]\n")
        try:
            proc = subprocess.run(aria_cmd)
            if proc.returncode == 0:
                self.console.print(f"\n✨ [bold green]Torrent download finished successfully in:[/bold green] [bold white]{dest_dir}[/bold white]")
            return proc.returncode
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]👋 Torrent download cancelled by user.[/bold yellow]")
            return 130
        except Exception as e:
            self.console.print(f"[bold red]Error running aria2c:[/bold red] {e}")
            return 1
