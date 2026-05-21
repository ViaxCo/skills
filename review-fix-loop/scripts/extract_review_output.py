#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract the authoritative review text from a review-fix-loop summary."
    )
    parser.add_argument("--summary", required=True, help="Path to summary.json from run_review.py")
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Print only the authoritative review text path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured metadata as JSON instead of raw review text",
    )
    args = parser.parse_args()

    summary_path = Path(args.summary).expanduser().resolve()
    summary = load_json(summary_path)
    review_text_path = summary.get("review_text_path")

    if not isinstance(review_text_path, str) or not review_text_path:
        payload = {
            "usable": False,
            "used_reviewer": summary.get("used_reviewer"),
            "stop_reason": summary.get("stop_reason"),
            "review_text_path": None,
            "review_text": None,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        elif args.print_path:
            print("")
        return 1

    review_path = Path(review_text_path)
    review_text = review_path.read_text(encoding="utf-8")
    payload = {
        "usable": True,
        "used_reviewer": summary.get("used_reviewer"),
        "stop_reason": summary.get("stop_reason"),
        "review_text_path": str(review_path),
        "review_text": review_text,
    }

    if args.print_path:
        print(review_path)
    elif args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(review_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
