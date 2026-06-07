"""
cli_ui.py — Colorized CLI output helpers.

Degrades gracefully to plain text when stdout is not a TTY.
Uses ANSI escape codes only — pure stdlib, no curses.
"""

import sys
import os


# ── TTY detection ──────────────────────────────────────────────────────────────

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


# ── ANSI codes ─────────────────────────────────────────────────────────────────

class _C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # Foreground
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"
    # Background
    BG_BLUE  = "\033[44m"
    BG_CYAN  = "\033[46m"


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI code if color is enabled."""
    if not _USE_COLOR:
        return text
    return f"{code}{text}{_C.RESET}"


# ── Public formatting helpers ──────────────────────────────────────────────────

def bold(text: str) -> str:
    return _c(_C.BOLD, text)

def dim(text: str) -> str:
    return _c(_C.DIM, text)

def green(text: str) -> str:
    return _c(_C.GREEN, text)

def yellow(text: str) -> str:
    return _c(_C.YELLOW, text)

def red(text: str) -> str:
    return _c(_C.RED, text)

def cyan(text: str) -> str:
    return _c(_C.CYAN, text)

def magenta(text: str) -> str:
    return _c(_C.MAGENTA, text)

def blue(text: str) -> str:
    return _c(_C.BLUE, text)

def gray(text: str) -> str:
    return _c(_C.GRAY, text)


# ── Structured output ──────────────────────────────────────────────────────────

def print_banner() -> None:
    """Print the application header banner."""
    width = 62
    border = "─" * width

    lines = [
        "",
        _c(_C.BOLD + _C.CYAN, f"╭{border}╮"),
        _c(_C.BOLD + _C.CYAN, "│") +
        _c(_C.BOLD + _C.WHITE, "  🎬  bili-fav-summarizer".center(width)) +
        _c(_C.BOLD + _C.CYAN, "│"),
        _c(_C.BOLD + _C.CYAN, "│") +
        _c(_C.DIM, "  Bilibili Favorites → Study Notes  ".center(width)) +
        _c(_C.BOLD + _C.CYAN, "│"),
        _c(_C.BOLD + _C.CYAN, f"╰{border}╯"),
        "",
    ]
    print("\n".join(lines))


def print_section(title: str) -> None:
    """Print a section divider."""
    marker = _c(_C.BOLD + _C.CYAN, "──")
    title_fmt = _c(_C.BOLD + _C.WHITE, f" {title} ")
    print(f"\n{marker}{title_fmt}{marker}")


def print_ok(msg: str) -> None:
    """Print a success line."""
    print(f"  {green('✓')} {msg}")


def print_skip(msg: str) -> None:
    """Print a skip line."""
    print(f"  {yellow('⏭')} {msg}")


def print_err(msg: str) -> None:
    """Print an error line."""
    print(f"  {red('✗')} {msg}")


def print_info(msg: str) -> None:
    """Print an informational line."""
    marker = _c(_C.BLUE, "·")
    print(f"  {marker} {msg}")


def print_progress(current: int, total: int, title: str, bvid: str = "") -> None:
    """Print a progress indicator for the current video."""
    counter = _c(_C.DIM, f"[{current}/{total}]")
    bvid_str = gray(f" ({bvid})") if bvid else ""
    title_short = title[:55] + ("…" if len(title) > 55 else "")
    print(f"\n{counter} {bold(title_short)}{bvid_str}")


def print_summary_box(
    total: int,
    summarized: int,
    no_subtitle: int,
    skipped_cache: int,
    errors: int,
    out_files: list[str],
) -> None:
    """Print the final run summary box."""
    width = 54
    border = "─" * width

    lines = [
        "",
        _c(_C.BOLD + _C.GREEN, f"╭{border}╮"),
        _c(_C.BOLD + _C.GREEN, "│") +
        _c(_C.BOLD + _C.WHITE, " Run Summary ".center(width)) +
        _c(_C.BOLD + _C.GREEN, "│"),
        _c(_C.BOLD + _C.GREEN, f"├{border}┤"),
    ]

    def row(label: str, value: str) -> str:
        pad = width - len(label) - len(value) - 2
        return (
            _c(_C.BOLD + _C.GREEN, "│") +
            f" {label}" + " " * max(pad, 1) + value + " " +
            _c(_C.BOLD + _C.GREEN, "│")
        )

    lines.append(row("Videos total:", bold(str(total))))
    lines.append(row("Summarized:", green(str(summarized))))
    if skipped_cache:
        lines.append(row("From cache:", cyan(str(skipped_cache))))
    lines.append(row("No subtitle:", yellow(str(no_subtitle))))
    if errors:
        lines.append(row("Errors:", red(str(errors))))

    lines.append(_c(_C.BOLD + _C.GREEN, f"├{border}┤"))
    for f in out_files:
        lines.append(row("Wrote:", dim(f)))
    lines.append(_c(_C.BOLD + _C.GREEN, f"╰{border}╯"))
    lines.append("")

    print("\n".join(lines))


def print_wrote(path: str) -> None:
    """Print a 'file written' confirmation."""
    print(f"  {cyan('→')} {dim(path)}")
