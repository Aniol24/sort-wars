"""
T2b — Algorithm Cache (SQLite)

Stores generated algorithms locally so we never pay to regenerate them.
Provides a pool of algorithms to pick from for each video duel.
"""

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.environ.get("DB_PATH", "./data/algorithms.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS algorithms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    valid       INTEGER NOT NULL DEFAULT 1,
    times_used  INTEGER NOT NULL DEFAULT 0,
    last_used   TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS duel_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    algo_a      TEXT    NOT NULL,
    algo_b      TEXT    NOT NULL,
    dueled_on   TEXT    NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Classic algorithms as seed — written directly (no API call needed for these)
# ---------------------------------------------------------------------------

_SEED_ALGORITHMS = [
    {
        "name": "Bubble Sort",
        "description": "Repeatedly swaps adjacent elements that are out of order, bubbling the largest to the end each pass.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [j, j + 1])
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swaps += 1
                yield (arr.copy(), comparisons, swaps, [j, j + 1])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Selection Sort",
        "description": "Scans for the minimum element and places it at the front, repeating for each position.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [j, min_idx])
            if arr[j] < arr[min_idx]:
                min_idx = j
        if min_idx != i:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
            swaps += 1
            yield (arr.copy(), comparisons, swaps, [i, min_idx])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Insertion Sort",
        "description": "Builds a sorted section one element at a time by inserting each new element into its correct position.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    for i in range(1, len(arr)):
        j = i
        while j > 0:
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [j - 1, j])
            if arr[j] < arr[j - 1]:
                arr[j], arr[j - 1] = arr[j - 1], arr[j]
                swaps += 1
                yield (arr.copy(), comparisons, swaps, [j - 1, j])
                j -= 1
            else:
                break
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Shell Sort",
        "description": "A gap-based insertion sort that starts with large gaps and shrinks them, allowing distant elements to move quickly.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    gap = n // 2
    while gap > 0:
        for i in range(gap, n):
            j = i
            while j >= gap:
                comparisons += 1
                yield (arr.copy(), comparisons, swaps, [j - gap, j])
                if arr[j] < arr[j - gap]:
                    arr[j], arr[j - gap] = arr[j - gap], arr[j]
                    swaps += 1
                    yield (arr.copy(), comparisons, swaps, [j - gap, j])
                    j -= gap
                else:
                    break
        gap //= 2
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Cocktail Shaker Sort",
        "description": "Bubble sort that alternates direction each pass, sweeping left then right to converge on a sorted array.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    left, right = 0, len(arr) - 1
    while left < right:
        for i in range(left, right):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, i + 1])
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swaps += 1
                yield (arr.copy(), comparisons, swaps, [i, i + 1])
        right -= 1
        for i in range(right, left, -1):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i - 1, i])
            if arr[i] < arr[i - 1]:
                arr[i], arr[i - 1] = arr[i - 1], arr[i]
                swaps += 1
                yield (arr.copy(), comparisons, swaps, [i - 1, i])
        left += 1
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Comb Sort",
        "description": "Bubble sort with a shrinking gap that eliminates turtles (small values near the end) efficiently.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    gap = n
    shrink = 1.3
    sorted_ = False
    while not sorted_:
        gap = int(gap / shrink)
        if gap <= 1:
            gap = 1
            sorted_ = True
        for i in range(n - gap):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, i + gap])
            if arr[i] > arr[i + gap]:
                arr[i], arr[i + gap] = arr[i + gap], arr[i]
                swaps += 1
                sorted_ = False
                yield (arr.copy(), comparisons, swaps, [i, i + gap])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Odd-Even Sort",
        "description": "Parallel-friendly sort that alternates between comparing odd-indexed and even-indexed adjacent pairs.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    sorted_ = False
    while not sorted_:
        sorted_ = True
        for i in range(0, n - 1, 2):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, i + 1])
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swaps += 1
                sorted_ = False
                yield (arr.copy(), comparisons, swaps, [i, i + 1])
        for i in range(1, n - 1, 2):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, i + 1])
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swaps += 1
                sorted_ = False
                yield (arr.copy(), comparisons, swaps, [i, i + 1])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Gnome Sort",
        "description": "A garden gnome that steps forward when happy with two elements, and shuffles back when not.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    i = 0
    while i < len(arr):
        if i == 0 or arr[i] >= arr[i - 1]:
            i += 1
        else:
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i - 1, i])
            arr[i], arr[i - 1] = arr[i - 1], arr[i]
            swaps += 1
            yield (arr.copy(), comparisons, swaps, [i - 1, i])
            i -= 1
        if i > 0:
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [max(0, i - 1), i])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Cycle Sort",
        "description": "Minimizes writes by detecting cycles in the permutation — each element moves exactly once to its final position.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    n = len(arr)
    for cycle_start in range(n - 1):
        item = arr[cycle_start]
        pos = cycle_start
        for i in range(cycle_start + 1, n):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, cycle_start])
            if arr[i] < item:
                pos += 1
        if pos == cycle_start:
            continue
        while item == arr[pos]:
            pos += 1
        arr[pos], item = item, arr[pos]
        swaps += 1
        yield (arr.copy(), comparisons, swaps, [pos, cycle_start])
        while pos != cycle_start:
            pos = cycle_start
            for i in range(cycle_start + 1, n):
                comparisons += 1
                yield (arr.copy(), comparisons, swaps, [i, cycle_start])
                if arr[i] < item:
                    pos += 1
            while item == arr[pos]:
                pos += 1
            arr[pos], item = item, arr[pos]
            swaps += 1
            yield (arr.copy(), comparisons, swaps, [pos, cycle_start])
    yield (arr.copy(), comparisons, swaps, [])""",
    },
    {
        "name": "Pancake Sort",
        "description": "Only allowed to flip prefixes of the array, like flipping stacks of pancakes to sort them by size.",
        "code": """def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0

    def flip(end):
        nonlocal swaps
        left, right = 0, end
        while left < right:
            arr[left], arr[right] = arr[right], arr[left]
            swaps += 1
            left += 1
            right -= 1

    for size in range(len(arr), 1, -1):
        max_idx = 0
        for i in range(1, size):
            comparisons += 1
            yield (arr.copy(), comparisons, swaps, [i, max_idx])
            if arr[i] > arr[max_idx]:
                max_idx = i
        if max_idx != size - 1:
            if max_idx != 0:
                flip(max_idx)
                yield (arr.copy(), comparisons, swaps, list(range(max_idx + 1)))
            flip(size - 1)
            yield (arr.copy(), comparisons, swaps, list(range(size)))
    yield (arr.copy(), comparisons, swaps, [])""",
    },
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def seed_database(force: bool = False) -> int:
    """Insert seed algorithms. Skips existing names. Returns count inserted."""
    conn = _connect()
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for algo in _SEED_ALGORITHMS:
        try:
            conn.execute(
                "INSERT INTO algorithms (name, description, code, created_at) VALUES (?, ?, ?, ?)",
                (algo["name"], algo["description"], algo["code"], now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            if force:
                conn.execute(
                    "UPDATE algorithms SET description=?, code=? WHERE name=?",
                    (algo["description"], algo["code"], algo["name"]),
                )
    conn.commit()
    conn.close()
    return inserted


def save_algorithm(name: str, description: str, code: str) -> int:
    """Save a generated algorithm. Returns its row id."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.execute(
            "INSERT INTO algorithms (name, description, code, created_at) VALUES (?, ?, ?, ?)",
            (name, description, code, now),
        )
        row_id = cur.lastrowid
    except sqlite3.IntegrityError:
        cur = conn.execute("SELECT id FROM algorithms WHERE name=?", (name,))
        row_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return row_id


def get_duel_pair(avoid_recent_days: int = 3) -> tuple[dict, dict]:
    """Pick two algorithms for a duel, avoiding recently used pairs."""
    conn = _connect()

    recent = conn.execute(
        "SELECT algo_a, algo_b FROM duel_history WHERE dueled_on >= date('now', ?)",
        (f"-{avoid_recent_days} days",),
    ).fetchall()
    recent_pairs = {(r["algo_a"], r["algo_b"]) for r in recent}
    recent_pairs |= {(b, a) for a, b in recent_pairs}

    rows = conn.execute(
        "SELECT * FROM algorithms WHERE valid=1 ORDER BY times_used ASC, RANDOM() LIMIT 20"
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        raise RuntimeError("Not enough algorithms in cache (need at least 2). Run seed first.")

    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if (a["name"], b["name"]) not in recent_pairs:
                return dict(a), dict(b)

    # All pairs recently used — just pick the two least used
    return dict(rows[0]), dict(rows[1])


def record_duel(algo_a_name: str, algo_b_name: str) -> None:
    conn = _connect()
    today = date.today().isoformat()
    conn.execute(
        "INSERT INTO duel_history (algo_a, algo_b, dueled_on) VALUES (?, ?, ?)",
        (algo_a_name, algo_b_name, today),
    )
    conn.execute(
        "UPDATE algorithms SET times_used = times_used + 1, last_used = ? WHERE name IN (?, ?)",
        (today, algo_a_name, algo_b_name),
    )
    conn.commit()
    conn.close()


def list_algorithms() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, name, description, valid, times_used, last_used, created_at FROM algorithms ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def invalidate_algorithm(name: str) -> None:
    conn = _connect()
    conn.execute("UPDATE algorithms SET valid=0 WHERE name=?", (name,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Algorithm cache management")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("seed", help="Populate DB with classic algorithms")
    sub.add_parser("list", help="List all algorithms in the cache")

    gen_p = sub.add_parser("generate", help="Generate N new algorithms via Claude API")
    gen_p.add_argument("n", type=int, nargs="?", default=1)

    inv_p = sub.add_parser("invalidate", help="Mark an algorithm as invalid")
    inv_p.add_argument("name")

    args = parser.parse_args()

    if args.cmd == "seed":
        n = seed_database()
        print(f"Seeded {n} algorithms into {DB_PATH}")

    elif args.cmd == "list":
        algos = list_algorithms()
        if not algos:
            print("Cache is empty. Run: python -m src.algorithm_cache seed")
            return
        print(f"{'ID':<4} {'Valid':<6} {'Used':<5} {'Name'}")
        print("-" * 60)
        for a in algos:
            valid = "✓" if a["valid"] else "✗"
            print(f"{a['id']:<4} {valid:<6} {a['times_used']:<5} {a['name']}")
            print(f"       {a['description'][:70]}")

    elif args.cmd == "generate":
        from src.algorithm_factory import generate_algorithm
        existing = [a["name"] for a in list_algorithms()]
        for i in range(args.n):
            print(f"Generating algorithm {i + 1}/{args.n}...")
            try:
                algo = generate_algorithm(avoid_names=existing)
                row_id = save_algorithm(algo["name"], algo["description"], algo["code"])
                existing.append(algo["name"])
                print(f"  [{row_id}] {algo['name']} — {algo['description']}")
            except RuntimeError as e:
                print(f"  FAILED: {e}")

    elif args.cmd == "invalidate":
        invalidate_algorithm(args.name)
        print(f"Invalidated: {args.name}")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
