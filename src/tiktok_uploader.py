"""
T6 — TikTok Uploader (Playwright)

Uploads a video to TikTok using a persistent browser session.
Session is saved after a one-time interactive login; subsequent runs
are fully headless.

Usage:
    # First-time login (opens a visible browser):
    python -m src.tiktok_uploader setup

    # Upload a video:
    python -m src.tiktok_uploader upload output/duel.mp4 "Title" "#tag1 #tag2"
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

load_dotenv()

SESSION_PATH = Path(os.environ.get("TIKTOK_SESSION_FILE", "./data/tiktok_session.json"))
LOGS_DIR     = Path(os.environ.get("LOGS_DIR", "./logs"))
UPLOAD_LOG   = LOGS_DIR / "uploads.jsonl"

UPLOAD_URL   = "https://www.tiktok.com/upload?lang=en"
MAX_ATTEMPTS = 3

# Centralised selectors — update here when TikTok changes their UI
_SEL = {
    # Hidden file input on the upload page
    "file_input":  "input[type='file']",
    # Caption editor — only visible once the video finishes processing
    "caption_box": "div[contenteditable='true']",
    # Post / publish button
    "post_btn":    "button[data-e2e='post-btn'], button:has-text('Post')",
}


# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(video_path: str, title: str, success: bool, error: str = "") -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts":    datetime.now(timezone.utc).isoformat(),
        "video": str(video_path),
        "title": title,
        "ok":    success,
        "error": error,
    }
    with open(UPLOAD_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ─── Session setup ────────────────────────────────────────────────────────────

def setup_session() -> None:
    """One-time interactive login. Opens a visible browser window."""
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.tiktok.com/login")
        print("Log in to TikTok in the browser window, then press Enter here...")
        input()
        context.storage_state(path=str(SESSION_PATH))
        browser.close()
    print(f"Session saved to {SESSION_PATH}")


# ─── Upload logic ─────────────────────────────────────────────────────────────

def _do_upload(page, video_path: str, caption: str) -> None:
    """Single upload attempt. Raises on any failure."""
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)  # let page JS initialise

    # Set the video file directly on the hidden input
    page.locator(_SEL["file_input"]).set_input_files(video_path)

    # Caption editor only becomes visible once TikTok finishes processing the video
    page.wait_for_selector(_SEL["caption_box"], timeout=120_000)
    page.wait_for_timeout(1000)  # let the editor fully initialise

    box = page.locator(_SEL["caption_box"]).first
    box.click()
    box.press("Control+a")          # clear any pre-filled placeholder
    box.type(caption, delay=30)     # type at human-ish speed

    page.locator(_SEL["post_btn"]).first.click()

    # TikTok redirects away from /upload on successful publish
    page.wait_for_url(lambda url: "/upload" not in url, timeout=30_000)


def upload_video(video_path: str, title: str, hashtags: list[str]) -> bool:
    """Upload with up to MAX_ATTEMPTS retries. Returns True on success."""
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not SESSION_PATH.exists():
        raise RuntimeError(
            f"No session file at {SESSION_PATH}. "
            "Run: python -m src.tiktok_uploader setup"
        )

    caption = title + "\n" + " ".join(hashtags)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_PATH))

        for attempt in range(1, MAX_ATTEMPTS + 1):
            page = context.new_page()
            try:
                _do_upload(page, video_path, caption)
                _log(video_path, title, success=True)
                browser.close()
                return True
            except (PlaywrightTimeout, Exception) as exc:
                err = str(exc)
                print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed: {err}")
                page.close()
                if attempt < MAX_ATTEMPTS:
                    time.sleep(2 ** attempt)  # 2 s, then 4 s
                else:
                    _log(video_path, title, success=False, error=err)

        browser.close()
    return False


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="TikTok uploader via Playwright")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("setup", help="One-time interactive login")

    up = sub.add_parser("upload", help="Upload a video")
    up.add_argument("video",    help="Path to the mp4 file")
    up.add_argument("title",    help="Caption title")
    up.add_argument("hashtags", nargs="*", help="#tag1 #tag2 ...")

    args = parser.parse_args()

    if args.cmd == "setup":
        setup_session()
    elif args.cmd == "upload":
        ok = upload_video(args.video, args.title, args.hashtags)
        print("Uploaded successfully" if ok else "Upload failed — check logs/uploads.jsonl")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
