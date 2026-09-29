"""Generate golden snapshots for the reasoning-params parity tests.

Run from the repo root (the project-root siada package must win over any
stale copy installed into site-packages):

    PYTHONPATH=. poetry run python tests/provider/_gen_reasoning_parity_golden.py

Outputs (next to this file):
    reasoning_parity_golden_responses.json      - ResponsesModel path (must stay identical)
    reasoning_parity_default_current.json       - default path snapshot of the CURRENT code
                                                  (reference; the refactor intentionally changed
                                                  this path by removing the OpenRouter-style
                                                  reasoning dict)
    reasoning_parity_default_before_refactor.json is a frozen copy of the default-path
    behavior BEFORE the refactor; the parity tests use it to prove claude/gemini are
    unchanged there.
"""

from __future__ import annotations

import json
from pathlib import Path

from reasoning_parity_harness import MODELS, VARIANTS, capture_all, is_unreachable

HERE = Path(__file__).parent


def main() -> None:
    golden_responses: dict[str, dict] = {}
    default_current: dict[str, dict] = {}

    for model in MODELS:
        for variant in VARIANTS:
            if is_unreachable(model, variant):
                print(f"skip unreachable {model}|{variant}")
                continue
            key = f"{model}|{variant}"
            snapshots = capture_all(model, variant)
            if "default" in snapshots:
                default_current[key] = snapshots["default"]
            else:
                golden_responses[key] = snapshots["responses"]
            print(f"captured {key}")

    (HERE / "reasoning_parity_golden_responses.json").write_text(
        json.dumps(golden_responses, indent=2, sort_keys=True, default=str) + "\n"
    )
    (HERE / "reasoning_parity_default_current.json").write_text(
        json.dumps(default_current, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(f"\nwrote {len(golden_responses)} responses snapshots, "
          f"{len(default_current)} default snapshots")


if __name__ == "__main__":
    main()
