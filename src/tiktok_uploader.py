"""
T6 — TikTok Uploader (Content Posting API)

Uploads a video to TikTok using the official Content Posting API.
Requires a valid OAuth token in data/tiktok_token.json (run tiktok_auth.py first).

Usage:
    python -m src.tiktok_uploader upload output/duel.mp4 "Title" "#tag1 #tag2"
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_PATH = Path("data/tiktok_token.json")
LOGS_DIR   = Path(os.environ.get("LOGS_DIR", "./logs"))
UPLOAD_LOG = LOGS_DIR / "uploads.jsonl"

MAX_ATTEMPTS   = 3
MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB per chunk

BASE_URL    = "https://open.tiktokapis.com/v2"
INIT_DIRECT_URL = f"{BASE_URL}/post/publish/video/init/"         # video.publish scope
INIT_INBOX_URL  = f"{BASE_URL}/post/publish/inbox/video/init/"    # video.upload scope
STATUS_URL      = f"{BASE_URL}/post/publish/status/fetch/"
REFRESH_URL = f"{BASE_URL}/oauth/token/refresh/"


# ─── Token management ─────────────────────────────────────────────────────────

def _load_token() -> dict:
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            f"No token file at {TOKEN_PATH}. Run: python tiktok_auth.py"
        )
    return json.loads(TOKEN_PATH.read_text())


def _refresh_token(token: dict) -> dict:
    from dotenv import dotenv_values
    env = dotenv_values()
    body = {
        "client_key":     env["TIKTOK_CLIENT_KEY"],
        "client_secret":  env["TIKTOK_CLIENT_SECRET"],
        "grant_type":     "refresh_token",
        "refresh_token":  token["refresh_token"],
    }
    resp = requests.post(
        REFRESH_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    new_token = resp.json()
    TOKEN_PATH.write_text(json.dumps(new_token, indent=2))
    return new_token


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


# ─── Upload logic ─────────────────────────────────────────────────────────────

def _init_upload(access_token: str, title: str, video_size: int, chunk_size: int, n_chunks: int) -> tuple[str, str]:
    """Initialize upload. Uses inbox endpoint (video.upload scope). Returns (publish_id, upload_url)."""
    resp = requests.post(
        INIT_INBOX_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title":                    title,
                "privacy_level":            "SELF_ONLY",
                "disable_duet":             False,
                "disable_comment":          False,
                "disable_stitch":           False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source":            "FILE_UPLOAD",
                "video_size":        video_size,
                "chunk_size":        chunk_size,
                "total_chunk_count": n_chunks,
            },
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"Init failed: {data}")
    return data["data"]["publish_id"], data["data"]["upload_url"]


def _upload_chunks(upload_url: str, video_bytes: bytes, chunk_size: int) -> None:
    total = len(video_bytes)
    offset = 0
    chunk_idx = 0
    while offset < total:
        chunk = video_bytes[offset: offset + chunk_size]
        end   = offset + len(chunk) - 1
        resp  = requests.put(
            upload_url,
            headers={
                "Content-Range":  f"bytes {offset}-{end}/{total}",
                "Content-Length": str(len(chunk)),
                "Content-Type":   "video/mp4",
            },
            data=chunk,
        )
        resp.raise_for_status()
        offset     += len(chunk)
        chunk_idx  += 1
        print(f"  Chunk {chunk_idx} uploaded ({offset}/{total} bytes)")


def _poll_status(access_token: str, publish_id: str, timeout: int = 120) -> str:
    """Poll until status is PUBLISH_COMPLETE or timeout. Returns final status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.post(
            STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        resp.raise_for_status()
        data   = resp.json()
        status = data.get("data", {}).get("status", "UNKNOWN")
        print(f"  Status: {status}")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"):
            return status
        time.sleep(3)
    return "TIMEOUT"


def upload_video(video_path: str, title: str, hashtags: list[str]) -> bool:
    """Upload video via Content Posting API. Returns True on success."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    caption      = title + " " + " ".join(hashtags)
    video_bytes  = path.read_bytes()
    video_size   = len(video_bytes)
    chunk_size   = min(video_size, MAX_CHUNK_SIZE)
    n_chunks     = -(-video_size // chunk_size)  # ceil division

    token = _load_token()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"Attempt {attempt}/{MAX_ATTEMPTS}...")
            publish_id, upload_url = _init_upload(
                token["access_token"], caption, video_size, chunk_size, n_chunks
            )
            print(f"  publish_id: {publish_id}")
            _upload_chunks(upload_url, video_bytes, chunk_size)
            status = _poll_status(token["access_token"], publish_id)
            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                _log(video_path, title, success=True)
                print(f"Uploaded successfully: {title}")
                return True
            raise RuntimeError(f"Publish ended with status: {status}")
        except Exception as exc:
            err = str(exc)
            print(f"Attempt {attempt} failed: {err}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 ** attempt)
            else:
                _log(video_path, title, success=False, error=err)

    return False


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="TikTok uploader via Content Posting API")
    sub    = parser.add_subparsers(dest="cmd")

    up = sub.add_parser("upload", help="Upload a video")
    up.add_argument("video",    help="Path to the mp4 file")
    up.add_argument("title",    help="Caption title")
    up.add_argument("hashtags", nargs="*", help="#tag1 #tag2 ...")

    args = parser.parse_args()

    if args.cmd == "upload":
        ok = upload_video(args.video, args.title, args.hashtags)
        print("Done" if ok else "Failed — check logs/uploads.jsonl")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
