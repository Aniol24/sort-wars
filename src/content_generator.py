"""
T5 — Content Generator

Assembles a VideoSpec for each duel:
  - picks two algorithms from the cache
  - picks a random initial array distribution
  - generates a TikTok title + hashtags via Claude API
"""

import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.algorithm_cache import get_duel_pair

load_dotenv()

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "./config/config.json"))

DISTRIBUTIONS = ["random", "reversed", "nearly_sorted", "sawtooth"]

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


@dataclass
class VideoSpec:
    algo_a: dict
    algo_b: dict
    array: list
    distribution: str
    title: str
    hashtags: list[str]
    config: dict = field(repr=False)


def _make_array(size: int, distribution: str) -> list:
    arr = list(range(1, size + 1))
    if distribution == "random":
        random.shuffle(arr)
    elif distribution == "reversed":
        arr = arr[::-1]
    elif distribution == "nearly_sorted":
        # Swap ~10% of elements so the array is almost but not quite sorted
        n_swaps = max(2, size // 10)
        for _ in range(n_swaps):
            i, j = random.randrange(size), random.randrange(size)
            arr[i], arr[j] = arr[j], arr[i]
    elif distribution == "sawtooth":
        half = size // 2
        arr = (list(range(1, half + 1)) * 2)[:size]
        random.shuffle(arr)
    return arr


def _generate_caption(algo_a: dict, algo_b: dict) -> tuple[str, list[str]]:
    """Generate TikTok title + hashtags via Claude API. Returns (title, hashtags)."""
    prompt = f"""\
Two sorting algorithms are competing in a head-to-head visualization:

Algorithm A: {algo_a['name']}
{algo_a['description']}

Algorithm B: {algo_b['name']}
{algo_b['description']}

Generate an engaging TikTok caption for this video. Respond with JSON only:
{{
  "title": "<captivating title, max 150 chars, no hashtags>",
  "hashtags": ["tag1", "tag2", ...]
}}

Rules:
- Title should create curiosity or debate about which algorithm wins
- 6-8 hashtags (no # prefix in the array values)
- Mix algo-specific and broad reach: sortingalgorithm, coding, algorithm, cs, computerscience, techtok, learnontiktok
- JSON only, no markdown, no extra text"""

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    data = json.loads(raw)
    title = data["title"][:150]
    hashtags = ["#" + h.lstrip("#") for h in data["hashtags"]]
    return title, hashtags


def _fallback_caption(algo_a: dict, algo_b: dict, config: dict) -> tuple[str, list[str]]:
    title = f"{algo_a['name']} vs {algo_b['name']} - which one wins?"
    hashtags = config.get("tiktok", {}).get("hashtags", [
        "#sortingalgorithm", "#coding", "#algorithm", "#cs",
        "#computerscience", "#techtok", "#learnontiktok",
    ])
    return title, hashtags


def generate_video_spec(
    distribution: str | None = None,
    avoid_recent_days: int = 3,
) -> VideoSpec:
    """Build a complete VideoSpec ready for rendering."""
    config = load_config()
    array_size = config["video"]["array_size"]

    if distribution is None:
        distribution = random.choice(DISTRIBUTIONS)

    algo_a, algo_b = get_duel_pair(avoid_recent_days=avoid_recent_days)
    array = _make_array(array_size, distribution)

    try:
        title, hashtags = _generate_caption(algo_a, algo_b)
    except Exception as e:
        print(f"Caption generation failed ({e}), using fallback")
        title, hashtags = _fallback_caption(algo_a, algo_b, config)

    return VideoSpec(
        algo_a=algo_a,
        algo_b=algo_b,
        array=array,
        distribution=distribution,
        title=title,
        hashtags=hashtags,
        config=config,
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Content generator — build a VideoSpec")
    parser.add_argument("--dist", choices=DISTRIBUTIONS, default=None,
                        help="Array distribution (default: random choice)")
    parser.add_argument("--no-api", action="store_true",
                        help="Skip Claude API call, use fallback caption")
    args = parser.parse_args()

    if args.no_api:
        os.environ.pop("ANTHROPIC_API_KEY", None)

    spec = generate_video_spec(distribution=args.dist)
    print(f"Duel:         {spec.algo_a['name']}  vs  {spec.algo_b['name']}")
    print(f"Distribution: {spec.distribution}  ({len(spec.array)} elements)")
    print(f"Title:        {spec.title}")
    print(f"Hashtags:     {' '.join(spec.hashtags)}")


if __name__ == "__main__":
    _cli()
