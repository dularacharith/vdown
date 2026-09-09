"""Automated dependency validation and installation module for simple-downloader.

Detects missing system dependencies (aria2c, ffmpeg) across Linux (pacman, apt, dnf, zypper),
macOS (brew), and Windows (winget, scoop, choco) and prompts the user to automate installation.
"""

import os
import platform
import shutil
import subprocess
import sys
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm


TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "aria2c": {
        "display": "aria2c (BitTorrent P2P Engine)",
        "purpose": "download torrents and magnet links at unthrottled peer-to-peer speeds",
        "packages": {
            "pacman": ["sudo", "pacman", "-S", "--noconfirm", "aria2"],
            "apt": ["sudo", "apt-get", "install", "-y", "aria2"],
            "dnf": ["sudo", "dnf", "install", "-y", "aria2"],
            "zypper": ["sudo", "zypper", "install", "-y", "aria2"],
            "brew": ["brew", "install", "aria2"],
            "winget": ["winget", "install", "Gyan.Breeze.aria2", "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            "scoop": ["scoop", "install", "aria2"],
            "choco": ["choco", "install", "-y", "aria2"],
        },
        "manual_cmds": {
            "pacman": "sudo pacman -S aria2",
            "apt": "sudo apt install aria2",
            "dnf": "sudo dnf install aria2",
            "zypper": "sudo zypper install aria2",
            "brew": "brew install aria2",
            "winget": "winget install Gyan.Breeze.aria2",
            "scoop": "scoop install aria2",
            "choco": "choco install aria2",
        },
    },
    "ffmpeg": {
        "display": "FFmpeg (Audio & Video Converter)",
        "purpose": "merge video streams, convert formats, and extract studio-quality audio",
        "packages": {
            "pacman": ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"],
            "apt": ["sudo", "apt-get", "install", "-y", "ffmpeg"],
            "dnf": ["sudo", "dnf", "install", "-y", "ffmpeg"],
            "zypper": ["sudo", "zypper", "install", "-y", "ffmpeg"],
            "brew": ["brew", "install", "ffmpeg"],
            "winget": ["winget", "install", "Gyan.FFmpeg", "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            "scoop": ["scoop", "install", "ffmpeg"],
            "choco": ["choco", "install", "-y", "ffmpeg"],
        },
        "manual_cmds": {
            "pacman": "sudo pacman -S ffmpeg",
            "apt": "sudo apt install ffmpeg",
            "dnf": "sudo dnf install ffmpeg",
            "zypper": "sudo zypper install ffmpeg",
            "brew": "brew install ffmpeg",
            "winget": "winget install Gyan.FFmpeg",
            "scoop": "scoop install ffmpeg",
            "choco": "choco install ffmpeg",
        },
    },
    "mpv": {
        "display": "mpv (Media Player)",
        "purpose": "stream and play audio and video directly in the CLI",
        "packages": {
            "pacman": ["sudo", "pacman", "-S", "--noconfirm", "mpv"],
            "apt": ["sudo", "apt-get", "install", "-y", "mpv"],
            "dnf": ["sudo", "dnf", "install", "-y", "mpv"],
            "zypper": ["sudo", "zypper", "install", "-y", "mpv"],
            "brew": ["brew", "install", "mpv"],
            "winget": ["winget", "install", "io-net.mpv", "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            "scoop": ["scoop", "install", "mpv"],
            "choco": ["choco", "install", "-y", "mpv"],
        },
        "manual_cmds": {
            "pacman": "sudo pacman -S mpv",
            "apt": "sudo apt install mpv",
            "dnf": "sudo dnf install mpv",
            "zypper": "sudo zypper install mpv",
            "brew": "brew install mpv",
            "winget": "winget install mpv",
            "scoop": "scoop install mpv",
            "choco": "choco install mpv",
        },
    },
}


def detect_package_manager() -> Optional[str]:
    """Detect available system package manager."""
    system = platform.system().lower()

    if system == "linux":
        if shutil.which("pacman"):
            return "pacman"
        elif shutil.which("apt-get") or shutil.which("apt"):
            return "apt"
        elif shutil.which("dnf"):
            return "dnf"
        elif shutil.which("zypper"):
            return "zypper"
    elif system == "darwin":
        if shutil.which("brew"):
            return "brew"
    elif system == "windows":
        if shutil.which("winget"):
            return "winget"
        elif shutil.which("scoop"):
            return "scoop"
        elif shutil.which("choco"):
            return "choco"

    return None


def is_tool_installed(tool_name: str) -> bool:
    """Check if a tool executable exists in PATH."""
    if tool_name == "aria2c":
        return shutil.which("aria2c") is not None or shutil.which("aria2") is not None
    return shutil.which(tool_name) is not None


def get_install_command_for_tool(tool_name: str) -> Tuple_Cmd:
    """Return (command_args, command_display_str, manager_name)."""
    spec = TOOL_SPECS.get(tool_name)
    if not spec:
        return None, None, None

    manager = detect_package_manager()
    if manager and manager in spec["packages"]:
        return spec["packages"][manager], spec["manual_cmds"][manager], manager

    # Generic fallbacks
    system = platform.system().lower()
    if system == "linux":
        return None, "sudo pacman -S aria2  # or: sudo apt install aria2", None
    elif system == "windows":
        return None, "winget install aria2", None
    elif system == "darwin":
        return None, "brew install aria2", None
    return None, f"Install {tool_name} for your operating system", None


Tuple_Cmd = tuple[Optional[List[str]], Optional[str], Optional[str]]


def ensure_tool_installed(
    tool_name: str,
    purpose: Optional[str] = None,
    console: Optional[Console] = None,
    interactive: bool = True,
) -> bool:
    """Validate that tool is installed. If missing, prompt user to automate installation.

    Returns:
        bool: True if tool is available or was successfully installed; False otherwise.
    """
    con = console or Console()

    if is_tool_installed(tool_name):
        return True

    spec = TOOL_SPECS.get(tool_name, {
        "display": tool_name,
        "purpose": purpose or "perform this operation",
    })
    tool_display = spec["display"]
    tool_purpose = purpose or spec["purpose"]
    cmd_args, cmd_str, manager = get_install_command_for_tool(tool_name)

    # If non-interactive / no TTY, display error and return False
    is_tty = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
    if not interactive or not is_tty:
        con.print(
            Panel(
                f"[bold red]Missing Dependency: {tool_display}[/bold red]\n\n"
                f"This tool is required to {tool_purpose}.\n\n"
                f"Install command:\n  [bold green]{cmd_str or 'Install via your package manager'}[/bold green]",
                title="[bold yellow]⚡ Dependency Missing[/bold yellow]",
                border_style="red",
            )
        )
        return False

    # Interactive prompt to automate installation
    con.print(
        Panel(
            f"[bold yellow]⚡ {tool_display} is not installed.[/bold yellow]\n\n"
            f"This tool is required to {tool_purpose}.\n\n"
            f"Automated install command ({manager or 'system'}):\n"
            f"  [bold green]{cmd_str}[/bold green]",
            title="[bold cyan]Dependency Validation[/bold cyan]",
            border_style="yellow",
        )
    )

    if not cmd_args:
        con.print(f"[dim]Automatic installation is not supported for your package manager. Please run the command above.[/dim]")
        return False

    prompt_text = f"Would you like to install {tool_display} automatically now?"
    if not Confirm.ask(prompt_text, default=True):
        con.print(f"[dim]Installation skipped. Run '[bold]{cmd_str}[/bold]' when ready.[/dim]")
        return False

    con.print(f"\n[bold cyan]🚀 Installing {tool_display}...[/bold cyan] [dim](enter sudo password if prompted)[/dim]\n")

    try:
        proc = subprocess.run(cmd_args)
        if proc.returncode == 0 or is_tool_installed(tool_name):
            con.print(f"\n✨ [bold green]✔ {tool_display} installed successfully![/bold green]\n")
            return True
        else:
            con.print(f"\n[bold red]✖ Installation exited with code {proc.returncode}.[/bold red]\n"
                      f"You can try running manually:\n  [bold yellow]{cmd_str}[/bold yellow]\n")
            return False
    except Exception as e:
        con.print(f"\n[bold red]✖ Failed to execute installer:[/bold red] {e}\n")
        return False
