#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def iter_events(text: str):
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def extract_review_output(events):
    last_agent_message = None
    for event in events:
        candidates = []
        for key in ("msg", "item", "payload"):
            value = event.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        candidates.append(event)

        for msg in candidates:
            if not isinstance(msg, dict):
                continue

            event_type = msg.get("type")
            if event_type == "exited_review_mode":
                review_output = msg.get("review_output")
                if isinstance(review_output, dict):
                    return {
                        "source": "exited_review_mode",
                        "review_output": review_output,
                    }

            if event_type == "agent_message":
                text = msg.get("message") or msg.get("text")
                if isinstance(text, str) and text.strip():
                    last_agent_message = text

            if event_type in {"turn_complete", "turn.completed"}:
                text = msg.get("last_agent_message")
                if isinstance(text, str) and text.strip():
                    last_agent_message = text

    if last_agent_message:
        return {
            "source": "agent_message",
            "review_output": {
                "overall_explanation": last_agent_message,
            },
        }

    return None


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: extract_review_output.py [jsonl_file]", file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    result = extract_review_output(iter_events(text))
    if result is None:
        print(
            json.dumps(
                {
                    "source": "missing_structured_review_output",
                    "error": "No final reviewer message found.",
                },
                indent=2,
            )
        )
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
