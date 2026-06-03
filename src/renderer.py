"""
T3 — Visual Renderer

Renders sorting algorithm duel videos: 1080x1920, 60fps, TikTok vertical.
Two algorithms compete side by side with live stats and a winner indicator.

Usage:
    python -m src.renderer preview          # generates preview.png at midpoint
    python -m src.renderer video            # renders full output/duel.mp4
"""

import colorsys
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

# ─── Canvas ───────────────────────────────────────────────────────────────────
W, H = 1080, 1920
FPS  = 60

# ─── Layout (pixels) ──────────────────────────────────────────────────────────
HEADER_H     = 210
NAMES_H      = 110
CHART_TOP    = HEADER_H + NAMES_H     # 320
CHART_BOTTOM = 1610
STATS_TOP    = CHART_BOTTOM
STATS_H      = H - STATS_TOP          # 310

L_X1, L_X2  = 20,  520               # left panel  (500px wide)
DIV_X1, DIV_X2 = 520, 560            # divider     (40px)
R_X1, R_X2  = 560, 1060              # right panel (500px wide)

# ─── Palette ──────────────────────────────────────────────────────────────────
BG          = (6,  6,  14)
HEADER_BG   = (10, 10, 24)
COLOR_A     = (0,  230, 255)          # cyan  — algorithm A
COLOR_B     = (255, 45, 120)          # pink  — algorithm B
COLOR_ACTIVE = (255, 255, 200)        # warm white — highlighted bars
COLOR_GOLD  = (255, 200, 0)
COLOR_TEXT  = (200, 215, 240)
COLOR_SUB   = (100, 115, 145)
COLOR_DIV   = (35,  35,  65)

HUE_A = 185.0   # cyan hue
HUE_B = 330.0   # pink hue

# ─── Fonts ────────────────────────────────────────────────────────────────────
_BOLD_PATHS = [
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_REG_PATHS = [
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

_font_cache: dict = {}

def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        paths = _BOLD_PATHS if bold else _REG_PATHS
        font = ImageFont.load_default()
        for p in paths:
            try:
                font = ImageFont.truetype(p, size)
                break
            except (IOError, OSError):
                pass
        _font_cache[key] = font
    return _font_cache[key]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _bar_color(value: int, max_val: int, hue: float, active: bool) -> tuple:
    if active:
        return COLOR_ACTIVE
    brightness = 0.20 + 0.80 * (value / max_val)
    r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.90, brightness)
    return (int(r * 255), int(g * 255), int(b * 255))


def _centered(draw: ImageDraw.Draw, cx: int, y: int, text: str,
               font: ImageFont.FreeTypeFont, fill: tuple) -> None:
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=fill)


def _draw_bars(draw: ImageDraw.Draw, array: list, active: set,
               hue: float, x1: int, x2: int, y_top: int, y_bot: int) -> None:
    n = len(array)
    if n == 0:
        return
    max_v = max(array)
    if max_v == 0:
        max_v = 1
    cw = x2 - x1
    ch = y_bot - y_top
    bw = cw / n

    for i, v in enumerate(array):
        bx1 = int(x1 + i * bw)
        bx2 = max(bx1 + 1, int(x1 + (i + 1) * bw) - 1)
        bh  = max(2, int(ch * v / max_v))
        color = _bar_color(v, max_v, hue, i in active)
        draw.rectangle([(bx1, y_bot - bh), (bx2, y_bot)], fill=color)


def _draw_stats(draw: ImageDraw.Draw, cx: int, y: int,
                color: tuple, comp: int, swaps: int,
                progress: float, leading: bool) -> None:
    # Leading badge
    if leading:
        badge_text = "LEADING"
        bb = draw.textbbox((0, 0), badge_text, font=_font(28))
        bw = bb[2] - bb[0] + 24
        bx = cx - bw // 2
        draw.rounded_rectangle([(bx, y), (bx + bw, y + 38)], radius=8, fill=color)
        _centered(draw, cx, y + 5, badge_text, _font(28), BG)
        y += 48

    # Comparison count
    draw.text((cx - 220, y), "COMPARISONS", font=_font(24, bold=False), fill=COLOR_SUB)
    draw.text((cx - 220, y + 28), f"{comp:,}", font=_font(58), fill=color)

    # Swaps count
    draw.text((cx - 220, y + 100), "SWAPS", font=_font(24, bold=False), fill=COLOR_SUB)
    draw.text((cx - 220, y + 128), f"{swaps:,}", font=_font(48), fill=color)

    # Progress bar
    bar_y = y + 188
    bx1, bx2 = cx - 220, cx + 220
    draw.rounded_rectangle([(bx1, bar_y), (bx2, bar_y + 10)], radius=5, fill=(25, 25, 45))
    filled = int((bx2 - bx1) * min(progress, 1.0))
    if filled > 2:
        draw.rounded_rectangle([(bx1, bar_y), (bx1 + filled, bar_y + 10)], radius=5, fill=color)


# ─── Frame renderer ───────────────────────────────────────────────────────────

def render_frame(
    arr_a: list, active_a: set, comp_a: int, swaps_a: int, done_a: bool,
    arr_b: list, active_b: set, comp_b: int, swaps_b: int, done_b: bool,
    name_a: str, name_b: str,
    progress_a: float, progress_b: float,
    winner: Optional[str] = None,
) -> Image.Image:

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    leading_a = (not done_a and not done_b and progress_a > progress_b) or (done_a and not done_b)
    leading_b = (not done_a and not done_b and progress_b > progress_a) or (done_b and not done_a)

    # ── Header ────────────────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (W, HEADER_H)], fill=HEADER_BG)
    _centered(draw, W // 2, 28,  "SORT  WARS",      _font(72),         COLOR_GOLD)
    _centered(draw, W // 2, 118, "ALGORITHM  DUEL", _font(34, bold=False), COLOR_SUB)
    draw.rectangle([(0, HEADER_H - 3), (W, HEADER_H)], fill=COLOR_GOLD)

    # ── Name plates ───────────────────────────────────────────────────────────
    name_cy = HEADER_H + 28
    _centered(draw, (L_X1 + L_X2) // 2, name_cy, name_a.upper(), _font(40), COLOR_A)
    _centered(draw, (R_X1 + R_X2) // 2, name_cy, name_b.upper(), _font(40), COLOR_B)
    _centered(draw, W // 2,              name_cy + 10, "VS",       _font(46), COLOR_TEXT)

    # ── Divider ───────────────────────────────────────────────────────────────
    draw.rectangle([(DIV_X1, CHART_TOP), (DIV_X2, CHART_BOTTOM)], fill=COLOR_DIV)

    # ── Bar charts ────────────────────────────────────────────────────────────
    _draw_bars(draw, arr_a, set(active_a), HUE_A, L_X1 + 4, L_X2 - 4, CHART_TOP + 4, CHART_BOTTOM - 4)
    _draw_bars(draw, arr_b, set(active_b), HUE_B, R_X1 + 4, R_X2 - 4, CHART_TOP + 4, CHART_BOTTOM - 4)

    # ── Status banners ────────────────────────────────────────────────────────
    if done_a:
        label = "WINNER!" if winner == name_a else "SORTED"
        clr   = COLOR_GOLD if winner == name_a else COLOR_A
        _centered(draw, (L_X1 + L_X2) // 2, CHART_TOP + 14, label, _font(50), clr)
    if done_b:
        label = "WINNER!" if winner == name_b else "SORTED"
        clr   = COLOR_GOLD if winner == name_b else COLOR_B
        _centered(draw, (R_X1 + R_X2) // 2, CHART_TOP + 14, label, _font(50), clr)

    # ── Stats panel ───────────────────────────────────────────────────────────
    draw.rectangle([(0, STATS_TOP), (W, H)], fill=(9, 9, 22))
    draw.rectangle([(0, STATS_TOP), (W, STATS_TOP + 2)], fill=COLOR_DIV)
    draw.rectangle([(W // 2 - 1, STATS_TOP + 12), (W // 2 + 1, H - 12)], fill=COLOR_DIV)

    stats_y = STATS_TOP + 16
    _draw_stats(draw, (L_X1 + L_X2) // 2, stats_y, COLOR_A, comp_a, swaps_a, progress_a, leading_a)
    _draw_stats(draw, (R_X1 + R_X2) // 2, stats_y, COLOR_B, comp_b, swaps_b, progress_b, leading_b)

    return img


# ─── Algorithm execution ──────────────────────────────────────────────────────

def _run_algorithm(code: str, array: list) -> list:
    """Execute algorithm code and collect all yielded states."""
    ns = {}
    exec(code, ns)
    return list(ns["sort"](array))


def _make_array(size: int = 64, distribution: str = "random") -> list:
    arr = list(range(1, size + 1))
    if distribution == "random":
        random.shuffle(arr)
    elif distribution == "reversed":
        arr = arr[::-1]
    elif distribution == "nearly_sorted":
        random.shuffle(arr[:size // 5])
    elif distribution == "sawtooth":
        half = size // 2
        arr = list(range(1, half + 1)) * 2
        arr = arr[:size]
        random.shuffle(arr)
    return arr


# ─── Video rendering ──────────────────────────────────────────────────────────

def render_video(
    algo_a: dict, algo_b: dict,
    array: Optional[list] = None,
    output_path: str = "output/duel.mp4",
) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if array is None:
        array = _make_array(64, "random")

    print(f"Running {algo_a['name']}...")
    states_a = _run_algorithm(algo_a["code"], array)
    print(f"Running {algo_b['name']}...")
    states_b = _run_algorithm(algo_b["code"], array)

    total = max(len(states_a), len(states_b))
    winner = algo_a["name"] if len(states_a) <= len(states_b) else algo_b["name"]
    # Add 3 second celebration hold
    total_frames = total + FPS * 3

    print(f"Rendering {total_frames} frames ({total_frames / FPS:.1f}s) → {output_path}")

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "pipe:0",
        "-vcodec", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "23", "-preset", "fast",
        output_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        for f in range(total_frames):
            idx = min(f, total - 1)
            sa = states_a[min(idx, len(states_a) - 1)]
            sb = states_b[min(idx, len(states_b) - 1)]

            done_a = idx >= len(states_a) - 1
            done_b = idx >= len(states_b) - 1

            prog_a = min(idx / max(len(states_a) - 1, 1), 1.0)
            prog_b = min(idx / max(len(states_b) - 1, 1), 1.0)

            frame = render_frame(
                arr_a=sa[0], active_a=sa[3], comp_a=sa[1], swaps_a=sa[2], done_a=done_a,
                arr_b=sb[0], active_b=sb[3], comp_b=sb[1], swaps_b=sb[2], done_b=done_b,
                name_a=algo_a["name"], name_b=algo_b["name"],
                progress_a=prog_a, progress_b=prog_b,
                winner=winner,
            )
            proc.stdin.write(np.array(frame).tobytes())

            if f % 300 == 0:
                print(f"  {f}/{total_frames} frames ({100*f//total_frames}%)")
    finally:
        proc.stdin.close()
        proc.wait()

    print(f"Done: {output_path}")
    return output_path


# ─── Preview (single PNG) ─────────────────────────────────────────────────────

def render_preview(
    algo_a: dict, algo_b: dict,
    array: Optional[list] = None,
    output_path: str = "preview.png",
    at_fraction: float = 0.5,
) -> str:
    if array is None:
        array = _make_array(64, "random")

    states_a = _run_algorithm(algo_a["code"], array)
    states_b = _run_algorithm(algo_b["code"], array)

    total = max(len(states_a), len(states_b))
    idx   = int(total * at_fraction)
    winner = algo_a["name"] if len(states_a) <= len(states_b) else algo_b["name"]

    sa = states_a[min(idx, len(states_a) - 1)]
    sb = states_b[min(idx, len(states_b) - 1)]

    done_a = idx >= len(states_a) - 1
    done_b = idx >= len(states_b) - 1

    frame = render_frame(
        arr_a=sa[0], active_a=sa[3], comp_a=sa[1], swaps_a=sa[2], done_a=done_a,
        arr_b=sb[0], active_b=sb[3], comp_b=sb[1], swaps_b=sb[2], done_b=done_b,
        name_a=algo_a["name"], name_b=algo_b["name"],
        progress_a=min(idx / max(len(states_a) - 1, 1), 1.0),
        progress_b=min(idx / max(len(states_b) - 1, 1), 1.0),
        winner=winner if (done_a or done_b) else None,
    )
    frame.save(output_path)
    print(f"Preview saved: {output_path}")
    return output_path


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Sort Wars renderer")
    parser.add_argument("mode", choices=["preview", "video"], nargs="?", default="preview")
    parser.add_argument("--algo-a", default=None, help="Algorithm name (uses cache if not set)")
    parser.add_argument("--algo-b", default=None, help="Algorithm name (uses cache if not set)")
    parser.add_argument("--size",   type=int, default=64)
    parser.add_argument("--dist",   default="random", choices=["random", "reversed", "nearly_sorted", "sawtooth"])
    parser.add_argument("--at",     type=float, default=0.5, help="Preview fraction (0-1)")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    from src.algorithm_cache import get_duel_pair, list_algorithms

    if args.algo_a and args.algo_b:
        algos = {a["name"]: a for a in list_algorithms()}
        algo_a = algos[args.algo_a]
        algo_b = algos[args.algo_b]
    else:
        algo_a, algo_b = get_duel_pair()

    array = _make_array(args.size, args.dist)
    print(f"Duel: {algo_a['name']}  vs  {algo_b['name']}")

    if args.mode == "preview":
        out = args.output or "preview.png"
        render_preview(algo_a, algo_b, array, out, at_fraction=args.at)
    else:
        out = args.output or os.environ.get("VIDEOS_OUTPUT_DIR", "output") + "/duel.mp4"
        render_video(algo_a, algo_b, array, out)


if __name__ == "__main__":
    _cli()
