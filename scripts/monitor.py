#!/usr/bin/env python3
"""Parallax Pipeline Monitor — Real-time TUI dashboard."""

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, SpinnerColumn
from rich.table import Table
from rich.text import Text

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "data" / "notizie.db"
LOG_PATH = PROJECT_DIR / "data" / "pipeline.log"
PREVIEW_PATH = PROJECT_DIR / "data" / "preview.html"

PIPELINE_STEPS = [
    ("Step 1", "Collect RSS feeds"),
    ("Step 2", "Analyze articles"),
    ("Step 3", "Generate preview"),
    ("Step 4", "Deploy to GitHub Pages"),
    ("Step 5", "Final status"),
]


def parse_log_state():
    """Parse pipeline.log tail to determine current pipeline state."""
    state = {
        "running": False,
        "started_at": None,
        "current_step": None,
        "step_status": {},  # step_num -> "ok" | "failed" | "running" | "pending"
        "progress": None,  # (current, total) for summarizer
        "last_progress_time": None,
        "last_line": "",
        "sub_step": None,  # "summarize" | "match" | "compare"
        "translation": None,  # {"lang": "IT", "current": 3, "total": 12, "done": ["EN"]}
        "summarize_total": None,  # total articles to summarize this run (from log)
        "summarize_start_time": None,  # when summarization actually started
        "compare_done": 0,  # comparisons generated this run
        "compare_skipped": 0,
    }

    if not LOG_PATH.exists():
        return state

    # Read file from end, searching for last "Pipeline started"
    try:
        with open(LOG_PATH, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            # Read last 8MB — matching/compare phases generate huge batch output
            chunk_size = min(file_size, 8_000_000)
            f.seek(file_size - chunk_size)
            raw = f.read().decode("utf-8", errors="replace")
        tail_lines = raw.splitlines()
    except Exception:
        return state

    # Find last "Pipeline started"
    last_start_idx = None
    for i, line in enumerate(tail_lines):
        if "Pipeline started" in line:
            last_start_idx = i

    if last_start_idx is None:
        return state

    # Filter out batch noise to keep things manageable
    run_lines = [
        l for l in tail_lines[last_start_idx:]
        if "Batches:" not in l
    ]
    state["running"] = True

    # Parse start time
    m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*Pipeline started", run_lines[0])
    if m:
        state["started_at"] = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")

    # Check if pipeline completed
    for line in run_lines:
        if "Pipeline complete" in line:
            state["running"] = False

    # Parse step statuses
    for line in run_lines:
        for step_num in range(1, 6):
            prefix = f"Step {step_num}"
            if f"{prefix}: OK" in line:
                state["step_status"][step_num] = "ok"
            elif f"{prefix}: FAILED" in line:
                state["step_status"][step_num] = "failed"
            elif f"{prefix}:" in line and step_num not in state["step_status"]:
                state["step_status"][step_num] = "running"
                state["current_step"] = step_num

    # Find the current running step (highest without ok/failed)
    for step_num in range(1, 6):
        if step_num not in state["step_status"]:
            state["step_status"][step_num] = "pending"
        elif state["step_status"][step_num] == "running":
            state["current_step"] = step_num

    # Parse summarizer: find total and start time from "Processing N unprocessed articles"
    for line in run_lines:
        m = re.search(r"Processing (\d+) unprocessed articles", line)
        if m:
            state["summarize_total"] = int(m.group(1))
            tm = re.search(r"(\d{2}:\d{2}:\d{2})", line)
            if tm and state["started_at"]:
                t = datetime.strptime(tm.group(1), "%H:%M:%S")
                state["summarize_start_time"] = state["started_at"].replace(
                    hour=t.hour, minute=t.minute, second=t.second
                )
            break

    # Parse last logged progress checkpoint (every 50 articles)
    for line in reversed(run_lines):
        m = re.search(r"Progress: (\d+)/(\d+) articles processed", line)
        if m:
            state["progress"] = (int(m.group(1)), int(m.group(2)))
            tm = re.search(r"(\d{2}:\d{2}:\d{2})", line)
            if tm and state["started_at"]:
                t = datetime.strptime(tm.group(1), "%H:%M:%S")
                state["last_progress_time"] = state["started_at"].replace(
                    hour=t.hour, minute=t.minute, second=t.second
                )
            break

    # Detect sub-step within analyze
    for line in reversed(run_lines):
        if "Step 3/3: Generating perspective comparisons" in line:
            state["sub_step"] = "compare"
            break
        elif "Step 2/3: Matching stories" in line:
            state["sub_step"] = "match"
            break
        elif "Step 1/3: Summarizing articles" in line:
            state["sub_step"] = "summarize"
            break

    # Parse summarization completion
    for line in run_lines:
        if "Summarization complete:" in line:
            if state["sub_step"] == "summarize":
                state["sub_step"] = "match"  # moved past summarize

    # Parse compare progress (sub-step 3/3 of analyze)
    compare_done = 0
    compare_skipped = 0
    for line in run_lines:
        if "Saved comparison for cluster" in line:
            compare_done += 1
        elif "skipping" in line and "Cluster" in line:
            compare_skipped += 1
    state["compare_done"] = compare_done
    state["compare_skipped"] = compare_skipped

    # Parse translation progress (Step 3)
    trans_langs = ["IT", "ES", "DE", "FR"]
    done_langs = []
    current_lang = None
    current_trans = 0
    total_trans = 0

    for line in run_lines:
        # [IT] Done: 0 cached, 12 new translations
        m = re.search(r"\[([A-Z]{2})\] Done:", line)
        if m:
            done_langs.append(m.group(1))
            continue
        # [IT] 3/12: cluster 38 (translating...)
        m = re.search(r"\[([A-Z]{2})\]\s+(\d+)/(\d+):", line)
        if m:
            current_lang = m.group(1)
            current_trans = int(m.group(2))
            total_trans = int(m.group(3))

    if current_lang and current_lang not in done_langs:
        state["translation"] = {
            "lang": current_lang,
            "current": current_trans,
            "total": total_trans,
            "done": done_langs,
        }
    elif done_langs:
        state["translation"] = {
            "lang": None,
            "current": 0,
            "total": 0,
            "done": done_langs,
        }

    # Last meaningful line (skip noise)
    noise = ("Batches:", "warnings.warn", "NotOpenSSLWarning", "urllib3", "warn(")
    for line in reversed(run_lines):
        stripped = line.strip()
        if stripped and not any(stripped.startswith(n) or n in stripped for n in noise):
            state["last_line"] = stripped[-120:]
            break

    return state


def get_db_stats():
    """Query database for current statistics."""
    stats = {
        "articles": 0,
        "processed": 0,
        "unprocessed": 0,
        "clusters": 0,
        "comparisons": 0,
        "sources_active": 0,
        "sources_by_region": [],
        "recent_articles": 0,
    }

    if not DB_PATH.exists():
        return stats

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        stats["articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        stats["processed"] = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=1").fetchone()[0]
        stats["unprocessed"] = conn.execute("SELECT COUNT(*) FROM articles WHERE processed=0").fetchone()[0]
        stats["clusters"] = conn.execute("SELECT COUNT(*) FROM story_clusters").fetchone()[0]
        stats["comparisons"] = conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0]
        stats["sources_active"] = conn.execute("SELECT COUNT(*) FROM sources WHERE active=1").fetchone()[0]

        stats["recent_articles"] = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE fetched_at > datetime('now', '-24 hours')"
        ).fetchone()[0]

        rows = conn.execute("""
            SELECT s.region, COUNT(a.id) as cnt
            FROM sources s LEFT JOIN articles a ON a.source_id = s.id
            WHERE s.active = 1
            GROUP BY s.region ORDER BY s.region
        """).fetchall()
        stats["sources_by_region"] = [(r["region"], r["cnt"]) for r in rows]

        conn.close()
    except Exception:
        pass

    return stats


def get_deploy_info():
    """Check last deploy time from preview.html."""
    if PREVIEW_PATH.exists():
        mtime = os.path.getmtime(PREVIEW_PATH)
        return datetime.fromtimestamp(mtime)
    return None


def build_step_indicator(state):
    """Build step-by-step status indicator."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("icon", width=2)
    table.add_column("step", width=8)
    table.add_column("desc")
    table.add_column("detail", justify="right")

    for i, (label, desc) in enumerate(PIPELINE_STEPS, 1):
        status = state["step_status"].get(i, "pending")
        if status == "ok":
            icon = Text("[bold green]OK[/]")
            style = "green"
        elif status == "failed":
            icon = Text("[bold red]!![/]")
            style = "red"
        elif status == "running":
            icon = Text("[bold yellow]>>[/]")
            style = "bold yellow"
        else:
            icon = Text("[dim]--[/]")
            style = "dim"

        detail = ""
        if i == 2 and status == "running" and state.get("sub_step"):
            sub = state["sub_step"]
            color = "yellow" if sub == "summarize" else "magenta" if sub == "compare" else "cyan"
            detail = f"[{color}]{sub}[/]"
        elif i == 3 and status == "running" and state.get("translation"):
            tr = state["translation"]
            if tr.get("lang"):
                detail = f"[yellow]{tr['lang']}[/]"
            elif tr.get("done"):
                detail = f"[green]done[/]"

        table.add_row(
            Text.from_markup(str(icon)),
            Text(label, style=style),
            Text(desc, style=style),
            Text.from_markup(detail) if detail else Text(""),
        )

    return table


def build_dashboard():
    """Build the full dashboard layout."""
    state = parse_log_state()
    db = get_db_stats()
    deploy_time = get_deploy_info()
    now = datetime.now()

    # --- Header ---
    if state["running"]:
        elapsed = now - state["started_at"] if state["started_at"] else timedelta(0)
        elapsed_str = str(elapsed).split(".")[0]
        header_text = f"[bold green]RUNNING[/] since {state['started_at'].strftime('%H:%M:%S') if state['started_at'] else '?'} ({elapsed_str})"
    elif state["started_at"]:
        header_text = f"[bold cyan]IDLE[/] — last run: {state['started_at'].strftime('%Y-%m-%d %H:%M')}"
    else:
        header_text = "[dim]No pipeline runs found[/]"

    header = Panel(
        Text.from_markup(f"  PARALLAX Pipeline Monitor\n  {header_text}"),
        title="[bold]parallax[/]",
        border_style="bright_blue",
    )

    # --- Steps Panel ---
    steps_table = build_step_indicator(state)
    steps_panel = Panel(steps_table, title="Pipeline Steps", border_style="blue")

    # --- Progress Panel ---
    progress_content = []
    if state["current_step"] == 2 and state.get("sub_step") == "summarize":
        # Use DB unprocessed for real-time current count (more accurate than log every-50 checkpoint)
        total = state["summarize_total"] or (state["progress"][1] if state["progress"] else 0)
        if total > 0:
            db_done = max(0, total - db["unprocessed"]) if db["unprocessed"] <= total else (state["progress"][0] if state["progress"] else 0)
            current = min(db_done, total)
            pct = current / total * 100
            bar_width = 25
            filled = int(bar_width * pct / 100)
            bar = f"[green]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/]"
            progress_content.append(f"  Summarize: {bar} {current}/{total} ({pct:.0f}%)")

            # ETA: use summarize_start_time for accurate rate
            ref_time = state["summarize_start_time"] or state["started_at"]
            if ref_time and current > 0:
                elapsed_sec = (now - ref_time).total_seconds()
                rate = current / max(1, elapsed_sec)
                if rate > 0:
                    remaining = (total - current) / rate
                    eta = now + timedelta(seconds=remaining)
                    progress_content.append(f"  ETA: ~{eta.strftime('%H:%M')} ({remaining/60:.0f} min remaining)")
                    progress_content.append(f"  Speed: ~{rate*60:.1f} articles/min")
    elif state.get("translation") and state["current_step"] == 3:
        tr = state["translation"]
        all_langs = ["IT", "ES", "DE", "FR"]

        # Show language badges: done = green, active = yellow, pending = dim
        badges = []
        for lang in all_langs:
            if lang in tr["done"]:
                badges.append(f"[green]{lang}[/]")
            elif lang == tr.get("lang"):
                badges.append(f"[bold yellow]{lang}[/]")
            else:
                badges.append(f"[dim]{lang}[/]")
        progress_content.append(f"  Translate: {' '.join(badges)}")

        if tr["lang"] and tr["total"] > 0:
            pct = tr["current"] / tr["total"] * 100
            bar_width = 25
            filled = int(bar_width * pct / 100)
            bar = f"[yellow]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/]"
            progress_content.append(f"  [{tr['lang']}] {bar} {tr['current']}/{tr['total']} ({pct:.0f}%)")
        elif tr["done"]:
            progress_content.append(f"  [green]{len(tr['done'])}/{len(all_langs)} languages done[/]")
    elif state["running"] and state["current_step"] == 2 and state.get("sub_step") == "compare":
        done = state["compare_done"]
        skipped = state["compare_skipped"]
        total_clusters = db["clusters"]
        # estimate: done+skipped out of total clusters
        processed = done + skipped
        if total_clusters > 0:
            pct = min(100, processed / total_clusters * 100)
            bar_width = 25
            filled = int(bar_width * pct / 100)
            bar = f"[magenta]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/]"
            progress_content.append(f"  Compare: {bar} {processed}/{total_clusters} ({pct:.0f}%)")
        progress_content.append(f"  [green]{done} generated[/]  [dim]{skipped} skipped[/]")
    elif state["running"] and state["current_step"] == 2 and state.get("sub_step") == "match":
        progress_content.append("  [cyan]Matching stories across sources...[/]")
        progress_content.append("  [dim](embedding only, fast)[/]")
    elif state["running"] and state["current_step"]:
        step_desc = PIPELINE_STEPS[state["current_step"] - 1][1] if state["current_step"] <= len(PIPELINE_STEPS) else ""
        progress_content.append(f"  {step_desc}...")
    else:
        progress_content.append("  [dim]No active task[/]")

    progress_panel = Panel(
        Text.from_markup("\n".join(progress_content)),
        title="Progress",
        border_style="yellow",
    )

    # --- DB Stats Panel ---
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("label", style="cyan", width=16)
    stats_table.add_column("value", justify="right", width=8)

    stats_table.add_row("Active sources", str(db["sources_active"]))
    stats_table.add_row("Total articles", f"{db['articles']:,}")
    stats_table.add_row("Processed", f"[green]{db['processed']:,}[/]")
    stats_table.add_row("Unprocessed", f"[yellow]{db['unprocessed']:,}[/]" if db["unprocessed"] > 0 else "0")
    stats_table.add_row("Story clusters", str(db["clusters"]))
    stats_table.add_row("Comparisons", str(db["comparisons"]))
    stats_table.add_row("Last 24h", str(db["recent_articles"]))

    stats_panel = Panel(stats_table, title="Database", border_style="green")

    # --- Region colors (used in layout) ---
    region_colors = {
        "WESTERN": "blue", "EASTERN": "yellow", "MIDDLE_EAST": "red",
        "RUSSIA": "magenta", "CHINESE": "cyan", "INDIAN": "green",
        "EUROPEAN": "bright_blue",
    }

    # --- Last log line ---
    last_line = state.get("last_line", "")
    if last_line:
        # Trim and clean for display
        last_line = re.sub(r"\[.*?\]", "", last_line).strip()[:100]
    log_panel = Panel(
        Text(last_line or "—", style="dim"),
        title="Last Log",
        border_style="dim",
    )

    # --- Compose layout ---
    layout = Layout()
    layout.split_column(
        Layout(header, name="header", size=5),
        Layout(name="body"),
        Layout(log_panel, name="footer", size=4),
    )

    layout["body"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=2),
    )

    layout["left"].split_column(
        Layout(steps_panel, name="steps", size=8),
        Layout(progress_panel, name="progress", size=6),
    )

    # Combine region + deploy into one panel
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("label", style="cyan", width=14)
    info_table.add_column("value", justify="right")

    for region, cnt in db["sources_by_region"]:
        color = region_colors.get(region.upper(), "white")
        info_table.add_row(Text(region, style=color), str(cnt))

    if deploy_time:
        age = now - deploy_time
        info_table.add_row(Text(""), Text(""))
        info_table.add_row(Text("Last preview", style="magenta"), deploy_time.strftime("%m-%d %H:%M"))
    else:
        info_table.add_row(Text("Last preview", style="magenta"), "none")

    info_panel = Panel(info_table, title="Regions & Deploy", border_style="cyan")

    layout["right"].split_column(
        Layout(stats_panel, name="stats"),
        Layout(info_panel, name="info"),
    )

    return layout


def main():
    console = Console()

    try:
        with Live(build_dashboard(), console=console, refresh_per_second=1, screen=False) as live:
            while True:
                time.sleep(4)
                try:
                    live.update(build_dashboard())
                except Exception as e:
                    pass  # keep showing last good state
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/]")


if __name__ == "__main__":
    main()
