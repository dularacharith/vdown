"""BitTorrent and Magnet download module for simple-downloader.

Provides high-speed peer-to-peer downloading for magnet links and .torrent files,
with pure Python torrent inspection, aria2c P2P acceleration, silent background execution,
live structured status tables, interactive pause/start/stop/delete controls, and direct CLI media streaming.
"""

import hashlib
import json
import os
import platform
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm

from simple_downloader.utils import format_bytes, format_duration, sanitize_filename
from simple_downloader.installer import ensure_tool_installed, is_tool_installed, get_install_command_for_tool


MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".flv", ".webm", ".m4v", ".wmv", ".ts",
    ".mp3", ".flac", ".wav", ".m4a", ".opus", ".ogg",
}


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


def find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_key_nonblocking() -> Optional[str]:
    """Read a single keypress without blocking if running in an interactive terminal."""
    if not sys.stdin.isatty():
        return None
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                return sys.stdin.read(1)
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return None


def render_progress_bar(percent: float, width: int = 16) -> str:
    """Render a visual filled text-based progress bar."""
    percent = max(0.0, min(100.0, percent))
    filled_len = int(round(width * percent / 100.0))
    filled = "█" * filled_len
    empty = "░" * (width - filled_len)
    return f"[cyan]{filled}{empty}[/cyan] [bold white]{percent:5.1f}%[/bold white]"


class Aria2RpcClient:
    """Lightweight pure-Python JSON-RPC client for aria2c daemon."""

    def __init__(self, port: int, secret: Optional[str] = None, host: str = "127.0.0.1"):
        self.url = f"http://{host}:{port}/jsonrpc"
        self.secret = secret
        self.req_id = 0

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        self.req_id += 1
        payload_params: List[Any] = []
        if self.secret:
            payload_params.append(f"token:{self.secret}")
        if params:
            payload_params.extend(params)

        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": str(self.req_id),
            "method": method,
            "params": payload_params,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "error" in data:
                    raise RuntimeError(f"aria2 RPC error: {data['error']}")
                return data.get("result")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to connect to aria2 RPC ({self.url}): {e}")

    def tell_active(self) -> List[Dict[str, Any]]:
        return self.call("aria2.tellActive") or []

    def tell_waiting(self, offset: int = 0, num: int = 10) -> List[Dict[str, Any]]:
        return self.call("aria2.tellWaiting", [offset, num]) or []

    def tell_stopped(self, offset: int = 0, num: int = 10) -> List[Dict[str, Any]]:
        return self.call("aria2.tellStopped", [offset, num]) or []

    def tell_status(self, gid: str) -> Dict[str, Any]:
        return self.call("aria2.tellStatus", [gid]) or {}

    def pause(self, gid: str) -> Any:
        return self.call("aria2.pause", [gid])

    def unpause(self, gid: str) -> Any:
        return self.call("aria2.unpause", [gid])

    def remove(self, gid: str) -> Any:
        return self.call("aria2.remove", [gid])

    def force_remove(self, gid: str) -> Any:
        return self.call("aria2.forceRemove", [gid])

    def shutdown(self) -> Any:
        try:
            return self.call("aria2.shutdown")
        except Exception:
            return None


class InteractiveTorrentController:
    """Interactive BitTorrent download controller with live structured table and pause/start/stop/delete."""

    def __init__(
        self,
        target: str,
        dest_dir: Path,
        connections: int = 16,
        console: Optional[Console] = None,
        verbose: bool = False,
    ):
        self.target = target.strip().strip("'\"")
        self.dest_dir = dest_dir
        self.connections = connections
        self.console = console or Console()
        self.verbose = verbose

    def run(self) -> int:
        """Run the interactive download loop."""
        port = find_free_port()
        log_file = tempfile.NamedTemporaryFile(prefix="vdown_aria2_", suffix=".log", delete=False)
        log_path = log_file.name
        log_file.close()

        aria_cmd = [
            "aria2c",
            "--enable-rpc=true",
            f"--rpc-listen-port={port}",
            "--rpc-listen-all=false",
            f"--dir={self.dest_dir}",
            "--enable-dht=true",
            "--bt-enable-lpd=true",
            "--bt-max-peers=60",
            f"--max-connection-per-server={self.connections}",
            f"--split={self.connections}",
            "--seed-time=0",
            "--summary-interval=0",
            "--quiet=true",
            f"--log={log_path}",
            "--log-level=warn",
            self.target,
        ]

        proc = subprocess.Popen(aria_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = Aria2RpcClient(port)

        # Wait for RPC server to become ready
        ready = False
        for _ in range(40):
            try:
                client.call("aria2.getVersion")
                ready = True
                break
            except Exception:
                time.sleep(0.1)

        if not ready:
            self.console.print("[bold red]Failed to establish communication with aria2c daemon.[/bold red]")
            try:
                proc.terminate()
            except Exception:
                pass
            return 1

        # Locate initial GID
        gid: Optional[str] = None
        for _ in range(50):
            active = client.tell_active()
            if active:
                gid = active[0].get("gid")
                break
            waiting = client.tell_waiting(0, 5)
            if waiting:
                gid = waiting[0].get("gid")
                break
            time.sleep(0.1)

        if not gid:
            self.console.print("[bold red]Failed to initialize torrent task in aria2c.[/bold red]")
            client.shutdown()
            try:
                proc.terminate()
            except Exception:
                pass
            return 1

        show_logs = self.verbose
        user_status_msg: Optional[str] = None
        is_paused = False
        was_deleted = False
        was_stopped = False
        exit_code = 0
        last_status_data: Dict[str, Any] = {}

        def build_renderable(status_data: Dict[str, Any]) -> Group:
            nonlocal is_paused, user_status_msg, show_logs
            status_str = status_data.get("status", "active")
            total_len = int(status_data.get("totalLength", 0))
            comp_len = int(status_data.get("completedLength", 0))
            dl_speed = int(status_data.get("downloadSpeed", 0))
            ul_speed = int(status_data.get("uploadSpeed", 0))
            seeds = int(status_data.get("numSeeders", 0))
            peers = int(status_data.get("connections", 0))
            files = status_data.get("files", [])

            # Determine display name
            bt_info = status_data.get("bittorrent", {}).get("info", {})
            name = bt_info.get("name")
            if not name and files:
                first_path = files[0].get("path")
                if first_path:
                    name = Path(first_path).name
            if not name:
                name = "Resolving Torrent Metadata..."

            # Percent & ETA
            percent = (comp_len / total_len * 100.0) if total_len > 0 else 0.0
            if total_len > comp_len and dl_speed > 0:
                eta_str = format_duration((total_len - comp_len) / dl_speed)
            elif comp_len >= total_len and total_len > 0:
                eta_str = "Complete"
            else:
                eta_str = "--:--"

            # Status badge
            if status_str == "paused" or is_paused:
                status_badge = "[bold yellow]⏸️ PAUSED[/bold yellow]"
            elif status_str == "complete":
                status_badge = "[bold green]✨ COMPLETE[/bold green]"
            elif status_str == "error":
                status_badge = "[bold red]❌ ERROR[/bold red]"
            elif dl_speed > 0:
                status_badge = "[bold green]⬇️ DOWNLOADING[/bold green]"
            elif total_len == 0:
                status_badge = "[bold magenta]🧲 METADATA[/bold magenta]"
            else:
                status_badge = "[bold cyan]🔗 CONNECTING[/bold cyan]"

            # Table Construction
            table = Table(
                title=f"🧲 BitTorrent Swarm Transfer: [bold white]{name}[/bold white]",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
                expand=True,
            )
            table.add_column("Item / File", style="cyan", no_wrap=True, ratio=3)
            table.add_column("Size", justify="right", style="green", ratio=1)
            table.add_column("Progress", justify="center", ratio=2)
            table.add_column("Speed", justify="right", style="bold cyan", ratio=1)
            table.add_column("Up", justify="right", style="dim", ratio=1)
            table.add_column("Seeds/Peers", justify="center", style="yellow", ratio=1)
            table.add_column("ETA", justify="right", style="blue", ratio=1)
            table.add_column("Status", justify="center", ratio=1)

            display_item = name if len(name) <= 38 else name[:35] + "..."
            size_display = format_bytes(total_len) if total_len > 0 else "Pending"
            progress_display = render_progress_bar(percent)
            speed_display = f"{format_bytes(dl_speed)}/s" if dl_speed > 0 else "0 B/s"
            up_display = f"{format_bytes(ul_speed)}/s" if ul_speed > 0 else "0 B/s"
            swarm_display = f"SD: {seeds} | CN: {peers}"

            table.add_row(
                display_item,
                size_display,
                progress_display,
                speed_display,
                up_display,
                swarm_display,
                eta_str,
                status_badge,
            )

            # Controls Bar
            controls_text = (
                "  Controls: [bold yellow][P][/bold yellow] Pause  "
                "[bold green][S][/bold green] Resume/Start  "
                "[bold red][X][/bold red] Stop  "
                "[bold magenta][D][/bold magenta] Delete  "
                "[bold blue][V][/bold blue] Toggle Logs"
            )

            elements: List[Any] = [table, Text.from_markup(controls_text)]

            if user_status_msg:
                elements.append(Text.from_markup(f"  {user_status_msg}"))

            # Verbose log panel if toggled
            if show_logs and os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                        lines = [line.strip() for line in lf.readlines() if line.strip()][-8:]
                    log_content = "\n".join(lines) if lines else "[dim]No warnings or errors logged yet.[/dim]"
                    elements.append(Panel(log_content, title="📋 aria2c Logs", border_style="dim"))
                except Exception:
                    pass

            return Group(*elements)

        try:
            with Live(build_renderable({}), console=self.console, refresh_per_second=4, transient=False) as live:
                while True:
                    # 1. Non-blocking keypress handling
                    key = read_key_nonblocking()
                    if key:
                        k = key.lower()
                        if k == "p":
                            try:
                                client.pause(gid)
                                is_paused = True
                                user_status_msg = "[bold yellow]⏸️ Download paused. Press [S] to resume.[/bold yellow]"
                            except Exception as e:
                                user_status_msg = f"[dim]Could not pause: {e}[/dim]"
                        elif k == "s":
                            try:
                                client.unpause(gid)
                                is_paused = False
                                user_status_msg = "[bold green]▶️ Download resumed.[/bold green]"
                            except Exception as e:
                                user_status_msg = f"[dim]Could not resume: {e}[/dim]"
                        elif k == "x":
                            try:
                                client.remove(gid)
                            except Exception:
                                pass
                            was_stopped = True
                            user_status_msg = "[bold red]⏹️ Download stopped by user.[/bold red]"
                            break
                        elif k == "d":
                            # Pause first, prompt confirmation
                            try:
                                client.pause(gid)
                            except Exception:
                                pass
                            live.stop()
                            if Confirm.ask("\n[bold red]⚠️ Are you sure you want to delete this download and all its files?[/bold red]", default=False, console=self.console):
                                try:
                                    client.force_remove(gid)
                                except Exception:
                                    pass
                                was_deleted = True
                                break
                            else:
                                try:
                                    client.unpause(gid)
                                except Exception:
                                    pass
                                user_status_msg = "[dim]Deletion cancelled; download resumed.[/dim]"
                                live.start()
                        elif k == "v":
                            show_logs = not show_logs
                            user_status_msg = f"[dim]Logs {'enabled' if show_logs else 'hidden'}.[/dim]"

                    # 2. Status poll via RPC
                    try:
                        status_data = client.tell_status(gid)
                    except Exception:
                        status_data = last_status_data

                    # If magnet metadata finished, follow the new download task GID
                    if status_data.get("followedBy"):
                        gid = status_data["followedBy"][0]
                        try:
                            status_data = client.tell_status(gid)
                        except Exception:
                            pass

                    last_status_data = status_data
                    status_str = status_data.get("status", "active")
                    total_len = int(status_data.get("totalLength", 0))
                    comp_len = int(status_data.get("completedLength", 0))

                    live.update(build_renderable(status_data))

                    # Check completion
                    if status_str == "complete" or (total_len > 0 and comp_len >= total_len):
                        exit_code = 0
                        break
                    elif status_str == "error":
                        err_msg = status_data.get("errorMessage", "Unknown aria2 error")
                        self.console.print(f"\n[bold red]❌ Torrent download encountered an error:[/bold red] {err_msg}")
                        exit_code = 1
                        break
                    elif status_str == "removed":
                        break

                    time.sleep(0.25)

        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]👋 Torrent download cancelled by user.[/bold yellow]")
            try:
                client.remove(gid)
            except Exception:
                pass
            exit_code = 130

        finally:
            client.shutdown()
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
            if os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass

        # Post-download handling
        if was_deleted:
            # Clean up files matching torrent in dest_dir
            deleted_count = 0
            if "files" in last_status_data:
                for f_info in last_status_data["files"]:
                    p_str = f_info.get("path")
                    if p_str and os.path.exists(p_str):
                        try:
                            if os.path.isfile(p_str):
                                os.remove(p_str)
                            elif os.path.isdir(p_str):
                                shutil.rmtree(p_str, ignore_errors=True)
                            aria2_ctrl = Path(p_str + ".aria2")
                            if aria2_ctrl.exists():
                                aria2_ctrl.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
            self.console.print(f"\n🗑️ [bold yellow]Torrent download cancelled and {deleted_count} file(s) removed from disk.[/bold yellow]")
            return 0

        if was_stopped:
            self.console.print(f"\n⏹️ [bold yellow]Torrent download stopped. Progress saved in:[/bold yellow] [bold white]{self.dest_dir}[/bold white]")
            return 0

        if exit_code == 0:
            final_name = last_status_data.get("bittorrent", {}).get("info", {}).get("name") or "Torrent download"
            total_size = int(last_status_data.get("totalLength", 0))
            self.console.print(
                f"\n✨ [bold green]Torrent download finished successfully![/bold green]\n"
                f"   [bold white]Item:[/bold white] {final_name}\n"
                f"   [bold white]Size:[/bold white] [green]{format_bytes(total_size)}[/green]\n"
                f"   [bold white]Destination:[/bold white] [cyan]{self.dest_dir}[/cyan]"
            )

        return exit_code


class TorrentStreamPlayer:
    """Streams torrent media directly to media players (mpv / ffplay) in real time."""

    def __init__(
        self,
        target: str,
        dest_dir: Path,
        connections: int = 16,
        console: Optional[Console] = None,
    ):
        self.target = target.strip().strip("'\"")
        self.dest_dir = dest_dir
        self.connections = connections
        self.console = console or Console()

    def run(self) -> int:
        """Stream the torrent media with sequential piece prioritization."""
        # Check player
        player = "mpv" if is_tool_installed("mpv") else ("ffplay" if is_tool_installed("ffplay") else None)
        if not player:
            if not ensure_tool_installed(
                "mpv",
                purpose="stream and play media directly in the CLI",
                console=self.console,
                interactive=True,
            ):
                return 1
            player = "mpv"

        port = find_free_port()
        log_file = tempfile.NamedTemporaryFile(prefix="vdown_stream_", suffix=".log", delete=False)
        log_path = log_file.name
        log_file.close()

        aria_cmd = [
            "aria2c",
            "--enable-rpc=true",
            f"--rpc-listen-port={port}",
            "--rpc-listen-all=false",
            f"--dir={self.dest_dir}",
            "--enable-dht=true",
            "--bt-enable-lpd=true",
            "--bt-max-peers=60",
            f"--max-connection-per-server={self.connections}",
            f"--split={self.connections}",
            "--bt-prioritize-piece=head=25M,tail=15M",
            "--file-allocation=trunc",
            "--summary-interval=0",
            "--quiet=true",
            f"--log={log_path}",
            "--log-level=warn",
            self.target,
        ]

        proc = subprocess.Popen(aria_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = Aria2RpcClient(port)

        ready = False
        for _ in range(40):
            try:
                client.call("aria2.getVersion")
                ready = True
                break
            except Exception:
                time.sleep(0.1)

        if not ready:
            self.console.print("[bold red]Failed to communicate with aria2c daemon for streaming.[/bold red]")
            try:
                proc.terminate()
            except Exception:
                pass
            return 1

        gid: Optional[str] = None
        for _ in range(50):
            active = client.tell_active()
            if active:
                gid = active[0].get("gid")
                break
            waiting = client.tell_waiting(0, 5)
            if waiting:
                gid = waiting[0].get("gid")
                break
            time.sleep(0.1)

        if not gid:
            self.console.print("[bold red]Failed to initialize torrent stream task.[/bold red]")
            client.shutdown()
            try:
                proc.terminate()
            except Exception:
                pass
            return 1

        self.console.print("\n[bold cyan]⏳ Connecting to swarm and buffering media stream...[/bold cyan]")
        buffer_threshold = 12 * 1024 * 1024  # 12 MB initial buffer
        media_path: Optional[Path] = None

        try:
            while True:
                time.sleep(0.3)
                try:
                    status_data = client.tell_status(gid)
                except Exception:
                    continue

                if status_data.get("followedBy"):
                    gid = status_data["followedBy"][0]
                    status_data = client.tell_status(gid)

                total_len = int(status_data.get("totalLength", 0))
                comp_len = int(status_data.get("completedLength", 0))
                dl_speed = int(status_data.get("downloadSpeed", 0))
                seeds = int(status_data.get("numSeeders", 0))
                peers = int(status_data.get("connections", 0))
                files = status_data.get("files", [])

                effective_target = min(buffer_threshold, total_len) if total_len > 0 else buffer_threshold
                buf_percent = (comp_len / effective_target * 100.0) if effective_target > 0 else 0.0

                buf_bar = render_progress_bar(min(100.0, buf_percent), width=20)
                speed_str = f"{format_bytes(dl_speed)}/s" if dl_speed > 0 else "0 B/s"

                self.console.print(
                    f"\r  Buffering: {buf_bar}  "
                    f"([green]{format_bytes(comp_len)}[/green] / [dim]{format_bytes(effective_target)}[/dim])  "
                    f"Speed: [bold cyan]{speed_str}[/bold cyan]  "
                    f"Seeds: [yellow]{seeds}[/yellow] | Peers: [dim]{peers}[/dim]   ",
                    end="",
                )

                # Check if buffer threshold reached and file exists
                if comp_len >= effective_target and files:
                    # Discover largest media file
                    candidates: List[Tuple[Path, int]] = []
                    for f in files:
                        p = Path(f.get("path", ""))
                        if p.suffix.lower() in MEDIA_EXTENSIONS and p.exists():
                            candidates.append((p, f.get("length", 0)))

                    if candidates:
                        candidates.sort(key=lambda x: int(x[1]), reverse=True)
                        media_path = candidates[0][0]
                        break

            self.console.print("\n")
            if not media_path or not media_path.exists():
                self.console.print("[bold red]Could not find media file to play.[/bold red]")
                return 1

            self.console.print(f"🎬 [bold green]Launching {player.upper()} player:[/bold green] [bold white]{media_path.name}[/bold white]\n")

            # Spawn player while aria2c continues streaming in background
            if player == "mpv":
                player_cmd = ["mpv", "--demuxer-readahead-secs=20", "--keep-open=yes", str(media_path)]
            else:
                player_cmd = ["ffplay", "-autoexit", str(media_path)]

            subprocess.run(player_cmd)

            # Once player exits, prompt user to keep or discard
            if sys.stdin.isatty():
                self.console.print("\n[bold cyan]Media playback ended.[/bold cyan]")
                self.console.print("  [1] 💾 [bold green]Keep file in downloads folder[/bold green] [Default]")
                self.console.print("  [2] 🗑️ [bold red]Discard and delete downloaded stream[/bold red]")
                choice = Prompt.ask("Select an option", choices=["1", "2"], default="1")
                if choice == "2":
                    try:
                        if media_path.exists():
                            if media_path.is_file():
                                media_path.unlink()
                            elif media_path.is_dir():
                                shutil.rmtree(media_path, ignore_errors=True)
                        aria_ctrl = Path(str(media_path) + ".aria2")
                        if aria_ctrl.exists():
                            aria_ctrl.unlink()
                        self.console.print("[yellow]🗑️ Streaming cache deleted.[/yellow]")
                    except Exception as e:
                        self.console.print(f"[dim]Could not delete cache: {e}[/dim]")
                else:
                    self.console.print(f"✨ [bold green]File saved at:[/bold green] [bold white]{media_path}[/bold white]")

            return 0

        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]👋 Streaming cancelled by user.[/bold yellow]")
            return 130
        finally:
            client.shutdown()
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
            if os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass


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
        stream: bool = False,
        interactive: bool = True,
        verbose: bool = False,
    ) -> int:
        """Download or stream a magnet link or .torrent file with unthrottled P2P speed."""
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

        # Stream mode
        if stream:
            player = TorrentStreamPlayer(
                target=target_clean,
                dest_dir=dest_dir,
                connections=connections,
                console=self.console,
            )
            return player.run()

        # Interactive / silent controller mode
        controller = InteractiveTorrentController(
            target=target_clean,
            dest_dir=dest_dir,
            connections=connections,
            console=self.console,
            verbose=verbose,
        )
        return controller.run()
