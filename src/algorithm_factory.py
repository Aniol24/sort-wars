"""
T2a — Claude Algorithm Factory

Calls the Anthropic API to generate sorting algorithms.
Each algorithm is a Python generator that yields visualization states.

State tuple: (array_snapshot: list[int], comparisons: int, swaps: int, active_indices: list[int])
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


SYSTEM_PROMPT = """\
You are a sorting algorithm designer specializing in visually interesting algorithms for animation.

Generate a Python sorting algorithm following this EXACT interface:

def sort(arr):
    arr = arr.copy()
    comparisons = 0
    swaps = 0
    # ... your logic ...
    yield (arr.copy(), comparisons, swaps, [i, j])

Interface contract:
- Function MUST be named `sort`
- Parameter `arr` is a list of integers — copy it immediately at the top
- Each yield must be a 4-tuple:
    (array_snapshot: list[int], comparisons: int, swaps: int, active_indices: list[int])
  - array_snapshot: always call arr.copy(), never yield a reference
  - comparisons: cumulative count of comparisons performed
  - swaps: cumulative count of swaps performed
  - active_indices: indices currently being compared/swapped (can be [] if none)
- NO imports allowed (pure Python only)
- Must terminate for any list of 20–100 integers
- Yield at every comparison or swap (required for smooth animation)
- The final yield must have the array fully sorted

Respond in EXACTLY this format — nothing before or after:
NAME: <creative algorithm name>
DESCRIPTION: <one sentence describing the algorithm's personality or behavior>
```python
def sort(arr):
    <your implementation>
```\
"""

_VALIDATION_HARNESS = """\
import json, sys

{code}

arr = json.loads(sys.argv[1])
try:
    states = list(sort(arr))
    if not states:
        print(json.dumps({{"ok": False, "error": "no states yielded"}}))
        sys.exit(0)
    last_arr = states[-1][0]
    print(json.dumps({{
        "ok": True,
        "sorted": last_arr == sorted(arr),
        "states": len(states)
    }}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e)}}))
"""

_TEST_ARRAY = [64, 34, 25, 12, 22, 11, 90, 45, 67, 3, 78, 56, 8, 19, 42, 33, 71, 5, 50, 16]


def _parse_response(text: str) -> dict:
    name_match = re.search(r"^NAME:\s*(.+)$", text, re.MULTILINE)
    desc_match = re.search(r"^DESCRIPTION:\s*(.+)$", text, re.MULTILINE)
    code_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)

    if not name_match:
        raise ValueError("Missing NAME field in response")
    if not desc_match:
        raise ValueError("Missing DESCRIPTION field in response")
    if not code_match:
        raise ValueError("Missing python code block in response")

    return {
        "name": name_match.group(1).strip(),
        "description": desc_match.group(1).strip(),
        "code": code_match.group(1).strip(),
    }


def _validate_code(code: str) -> tuple[bool, str]:
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    if "def sort(" not in code:
        return False, "No sort() function found"

    harness = _VALIDATION_HARNESS.format(code=code)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(harness)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path, json.dumps(_TEST_ARRAY)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False, f"Runtime error: {result.stderr[:300]}"

        data = json.loads(result.stdout.strip())

        if not data.get("ok"):
            return False, f"Algorithm error: {data.get('error', 'unknown')}"
        if not data.get("sorted"):
            return False, "Algorithm does not correctly sort the array"
        if data.get("states", 0) < 10:
            return False, f"Too few animation states ({data.get('states')}), yield more often"

        return True, ""

    except subprocess.TimeoutExpired:
        return False, "Algorithm timed out (>10s for 20 elements)"
    except json.JSONDecodeError:
        return False, f"Invalid harness output: {result.stdout[:200]}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def generate_algorithm(avoid_names: list[str] | None = None, max_retries: int = 3) -> dict:
    """Generate a validated sorting algorithm via Claude API.

    Returns dict with keys: name, description, code
    Raises RuntimeError if all retries are exhausted.
    """
    client = _get_client()

    avoid_clause = ""
    if avoid_names:
        avoid_clause = f"\nDo NOT generate algorithms similar to: {', '.join(avoid_names)}."

    base_prompt = (
        "Generate a unique and visually interesting sorting algorithm."
        " It can be a known algorithm, an invented one, or a creative variation."
        " Prioritize algorithms that produce interesting visual movement patterns when animated."
        + avoid_clause
    )

    last_error = ""
    for attempt in range(max_retries):
        prompt = base_prompt
        if last_error:
            prompt += f"\n\nYour previous attempt failed validation: {last_error}\nFix the issue."

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text

        try:
            parsed = _parse_response(raw)
        except ValueError as e:
            last_error = str(e)
            continue

        valid, error = _validate_code(parsed["code"])
        if valid:
            return parsed

        last_error = error

    raise RuntimeError(
        f"Failed to generate a valid algorithm after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


if __name__ == "__main__":
    print("Generating algorithm via Claude API...")
    algo = generate_algorithm()
    print(f"\nName:        {algo['name']}")
    print(f"Description: {algo['description']}")
    print(f"\n--- Code ---\n{algo['code']}\n")
    print("Validation: PASSED")
