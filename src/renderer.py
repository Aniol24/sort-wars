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

# ─── Layout — vertical stacking (A above B) ───────────────────────────────────
PAD_TOP     = 130                           # top breathing room
PAD_SIDE    = 130                           # left/right padding
PAD_BOT     = 130                           # bottom breathing room
TITLE_H     = 80

A_HEADER_H  = 185
A_CHART_H   = 430

VS_H        = 110

B_HEADER_H  = 185
B_CHART_H   = 430

# Derived Y positions
A_HEADER_Y  = PAD_TOP + TITLE_H                  # 210
A_CHART_Y   = A_HEADER_Y + A_HEADER_H            # 395
A_CHART_BOT = A_CHART_Y + A_CHART_H              # 825

VS_Y        = A_CHART_BOT                         # 825
VS_BOT      = VS_Y + VS_H                         # 935

B_HEADER_Y  = VS_BOT                              # 935
B_CHART_Y   = B_HEADER_Y + B_HEADER_H            # 1120
B_CHART_BOT = B_CHART_Y + B_CHART_H              # 1550
# bottom margin: 1920 - 1550 = 370px (> PAD_BOT ✓)

CHART_X1    = PAD_SIDE                            # 130
CHART_X2    = W - PAD_SIDE                        # 950
BAR_MAX_FRAC = 0.58                               # bars cap at 58% of panel height

# ─── Palette ──────────────────────────────────────────────────────────────────
BG           = (5,   5,   8)
COLOR_A      = (0,  220, 110)         # terminal green
COLOR_B      = (255,  65,  65)        # error red
COLOR_ACTIVE = (255, 255, 255)        # white flash on active bars
COLOR_TITLE  = (220, 220, 230)        # off-white title
COLOR_SUB    = (55,  58,  78)         # dark label
COLOR_DIV    = (18,  18,  26)         # near-invisible divider

HUE_A = 142.0   # green
HUE_B =   0.0   # red

# ─── Fonts (monospace first) ──────────────────────────────────────────────────
_BOLD_PATHS = [
    "/usr/share/fonts/TTF/JetBrainsMono-Bold.ttf",
    "/usr/share/fonts/truetype/JetBrainsMono/JetBrainsMono-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_REG_PATHS = [
    "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/truetype/JetBrainsMono/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
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
    ch = int((y_bot - y_top) * BAR_MAX_FRAC)   # cap bar height
    bw = cw / n

    for i, v in enumerate(array):
        bx1 = int(x1 + i * bw)
        bx2 = max(bx1 + 1, int(x1 + (i + 1) * bw) - 1)
        bh  = max(2, int(ch * v / max_v))
        color = _bar_color(v, max_v, hue, i in active)
        draw.rectangle([(bx1, y_bot - bh), (bx2, y_bot)], fill=color)


def _draw_algo_header(draw: ImageDraw.Draw, y: int, name: str, comp: int,
                      color: tuple, leading: bool, done: bool, winner: str) -> None:
    cx = W // 2
    slug = name.lower().replace(" ", "_")

    _centered(draw, cx, y + 10, slug, _font(74), color)

    if done:
        label = "[ winner ]" if winner == name else "[ sorted ]"
        _centered(draw, cx, y + 110, label, _font(44, bold=False), color)
    else:
        _centered(draw, cx, y + 110, f"{comp:,} ops", _font(50, bold=False), color)
        if leading:
            bb = draw.textbbox((0, 0), slug, font=_font(74))
            nw = bb[2] - bb[0]
            ux = cx - nw // 2
            draw.rounded_rectangle([(ux, y + 94), (ux + nw, y + 99)], radius=2, fill=color)


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

    # ── Title ─────────────────────────────────────────────────────────────────
    _centered(draw, W // 2, PAD_TOP + 8, "sort_wars", _font(62, bold=False), COLOR_SUB)

    # ── Algo A header ─────────────────────────────────────────────────────────
    _draw_algo_header(draw, A_HEADER_Y, name_a, comp_a, COLOR_A, leading_a, done_a, winner or "")

    # ── Algo A bars ───────────────────────────────────────────────────────────
    _draw_bars(draw, arr_a, set(active_a), HUE_A, CHART_X1, CHART_X2, A_CHART_Y, A_CHART_BOT)

    # ── VS divider ────────────────────────────────────────────────────────────
    mid_y = VS_Y + VS_H // 2
    draw.rectangle([(40, mid_y - 1), (W // 2 - 70, mid_y + 1)], fill=COLOR_DIV)
    draw.rectangle([(W // 2 + 70, mid_y - 1), (W - 40, mid_y + 1)], fill=COLOR_DIV)
    _centered(draw, W // 2, mid_y - 30, "vs", _font(52, bold=False), COLOR_SUB)

    # ── Algo B header ─────────────────────────────────────────────────────────
    _draw_algo_header(draw, B_HEADER_Y, name_b, comp_b, COLOR_B, leading_b, done_b, winner or "")

    # ── Algo B bars ───────────────────────────────────────────────────────────
    _draw_bars(draw, arr_b, set(active_b), HUE_B, CHART_X1, CHART_X2, B_CHART_Y, B_CHART_BOT)

    return img


# ─── Algorithm execution ──────────────────────────────────────────────────────

def _run_algorithm(code: str, array: list) -> list:
    """Execute algorithm code and collect all yielded states."""
    ns = {}
    exec(code, ns)
    return list(ns["sort"](array))


def _make_array(size: int = 32, distribution: str = "random") -> list:
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

    print(f"Rendering {total_frames} frames ({total_frames / FPS:.1f}s) -> {output_path}")

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
    parser.add_argument("--size",   type=int, default=32)
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
