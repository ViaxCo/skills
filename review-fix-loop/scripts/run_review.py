#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 900


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def repo_dirty() -> bool:
    result = run_git(["status", "--porcelain=v1", "--untracked-files=all"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return bool(result.stdout.strip())


def current_branch() -> str:
    result = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git rev-parse failed")
    return result.stdout.strip()


def detect_base_ref() -> str | None:
    gh = subprocess.run(
        ["gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"],
        check=False,
        capture_output=True,
        text=True,
    )
    if gh.returncode == 0 and gh.stdout.strip():
        return f"origin/{gh.stdout.strip()}"

    for candidate in ("origin/main", "origin/master"):
        result = run_git(["show-ref", "--verify", f"refs/remotes/{candidate}"])
        if result.returncode == 0:
            return candidate
    return None


def detect_scope(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.scope == "uncommitted":
        return "uncommitted", None
    if args.scope == "base":
        if not args.base:
            raise RuntimeError("--base is required when --scope base is used")
        return "base", args.base
    if args.scope == "commit":
        if not args.commit:
            raise RuntimeError("--commit is required when --scope commit is used")
        return "commit", args.commit

    if repo_dirty():
        return "uncommitted", None

    branch = current_branch()
    if branch not in {"main", "master", "HEAD"}:
        base_ref = detect_base_ref()
        if base_ref:
            return "base", base_ref

    return "commit", "HEAD"


def scope_args(scope: str, value: str | None) -> list[str]:
    if scope == "uncommitted":
        return ["--uncommitted"]
    if scope == "base":
        return ["--base", value or ""]
    if scope == "commit":
        return ["--commit", value or ""]
    raise ValueError(f"unknown scope: {scope}")


def load_jsonl(path: Path) -> list[dict]:
    events: list[dict] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def find_nested_string(node, keys: tuple[str, ...]) -> str | None:
    if not keys:
        return node.strip() if isinstance(node, str) and node.strip() else None
    if not isinstance(node, dict):
        return None
    child = node.get(keys[0])
    return find_nested_string(child, keys[1:])


def extract_review_text(jsonl_path: Path, final_message_path: Path) -> tuple[str | None, str | None]:
    for event in load_jsonl(jsonl_path):
        review_output = first_non_empty(
            [
                find_nested_string(event, ("exited_review_mode", "review_output")),
                find_nested_string(event, ("payload", "exited_review_mode", "review_output")),
                find_nested_string(event, ("data", "exited_review_mode", "review_output")),
            ]
        )
        if review_output:
            return "structured_review_output", review_output

        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return "item_agent_message", text.strip()

    if final_message_path.exists():
        final_message = final_message_path.read_text(encoding="utf-8").strip()
        if final_message:
            return "final_reviewer_message", final_message

    for event in reversed(load_jsonl(jsonl_path)):
        final_message = first_non_empty(
            [
                find_nested_string(event, ("agent_message", "message")),
                find_nested_string(event, ("payload", "agent_message", "message")),
                find_nested_string(event, ("data", "agent_message", "message")),
                find_nested_string(event, ("message",)),
            ]
        )
        if final_message:
            return "jsonl_agent_message", final_message

    return None, None


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_command(
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> tuple[int | None, bool]:
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                timeout=timeout_seconds,
            )
            return completed.returncode, False
        except subprocess.TimeoutExpired:
            return None, True


def classify_failure(exit_code: int | None, timed_out: bool) -> str:
    if timed_out:
        return "reviewer_timeout"
    if exit_code is None:
        return "missing_reviewer_output"
    if exit_code != 0:
        return "reviewer_nonzero_exit"
    return "missing_reviewer_output"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Codex review with local-first scope detection and structured fallback handling."
    )
    parser.add_argument("--output-dir", required=True, help="Directory for reviewer outputs")
    parser.add_argument(
        "--scope",
        default="auto",
        choices=("auto", "uncommitted", "base", "commit"),
        help="Review scope selection mode",
    )
    parser.add_argument("--base", help="Base ref when --scope base is used")
    parser.add_argument("--commit", help="Commit ref when --scope commit is used")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable backup codex review after terminal preferred-review failure",
    )
    parser.add_argument("--title", help="Optional review title")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"

    scope, scope_value = detect_scope(args)
    selected_scope_args = scope_args(scope, scope_value)

    preferred_stdout = output_dir / "preferred.jsonl"
    preferred_stderr = output_dir / "preferred.stderr"
    preferred_message = output_dir / "preferred.last-message.txt"
    preferred_review = output_dir / "preferred.review.txt"

    summary: dict[str, object] = {
        "state": "running",
        "scope": scope,
        "scope_value": scope_value,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "preferred": {
            "command": None,
            "stdout_path": str(preferred_stdout),
            "stderr_path": str(preferred_stderr),
            "final_message_path": str(preferred_message),
            "review_text_path": None,
            "exit_code": None,
            "timed_out": False,
            "usable": False,
            "review_source": None,
        },
        "used_reviewer": "preferred",
        "backup": None,
        "review_text_path": None,
        "stop_reason": None,
    }

    preferred_command = [
        "codex",
        "exec",
        "review",
        "--json",
        "--output-last-message",
        str(preferred_message),
        *selected_scope_args,
    ]
    if args.title:
        preferred_command.extend(["--title", args.title])
    summary["preferred"]["command"] = preferred_command
    write_json(summary_path, summary)

    preferred_exit_code, preferred_timed_out = run_command(
        preferred_command,
        preferred_stdout,
        preferred_stderr,
        DEFAULT_TIMEOUT_SECONDS,
    )

    review_source = None
    preferred_usable = False
    if not preferred_timed_out and preferred_exit_code == 0:
        review_source, review_text = extract_review_text(preferred_stdout, preferred_message)
        if review_text:
            write_text(preferred_review, review_text)
            preferred_usable = True

    summary["preferred"]["review_text_path"] = str(preferred_review) if preferred_review.exists() else None
    summary["preferred"]["exit_code"] = preferred_exit_code
    summary["preferred"]["timed_out"] = preferred_timed_out
    summary["preferred"]["usable"] = preferred_usable
    summary["preferred"]["review_source"] = review_source

    if preferred_usable:
        summary["state"] = "completed"
        summary["review_text_path"] = str(preferred_review)
        summary["stop_reason"] = "review_ok"
        write_json(summary_path, summary)
        print(summary_path)
        return 0

    if args.no_fallback:
        summary["state"] = "completed"
        summary["review_text_path"] = None
        summary["stop_reason"] = classify_failure(preferred_exit_code, preferred_timed_out)
        write_json(summary_path, summary)
        print(summary_path)
        return 0

    backup_stdout = output_dir / "backup.stdout.txt"
    backup_stderr = output_dir / "backup.stderr"
    backup_review = output_dir / "backup.review.txt"
    summary["state"] = "running_backup"

    backup_command = ["codex", "review", *selected_scope_args]
    if args.title:
        backup_command.extend(["--title", args.title])

    backup_exit_code, backup_timed_out = run_command(
        backup_command,
        backup_stdout,
        backup_stderr,
        DEFAULT_TIMEOUT_SECONDS,
    )

    backup_usable = False
    if not backup_timed_out and backup_exit_code == 0:
        review_text = backup_stdout.read_text(encoding="utf-8").strip()
        if review_text:
            write_text(backup_review, review_text)
            backup_usable = True

    summary["used_reviewer"] = "backup" if backup_usable else "preferred"
    summary["backup"] = {
        "command": backup_command,
        "stdout_path": str(backup_stdout),
        "stderr_path": str(backup_stderr),
        "review_text_path": str(backup_review) if backup_review.exists() else None,
        "exit_code": backup_exit_code,
        "timed_out": backup_timed_out,
        "usable": backup_usable,
        "review_source": "backup_stdout" if backup_usable else None,
    }
    if backup_usable:
        summary["state"] = "completed"
        summary["review_text_path"] = str(backup_review)
        summary["stop_reason"] = "review_ok"
    else:
        summary["state"] = "completed"
        summary["review_text_path"] = None
        summary["stop_reason"] = classify_failure(preferred_exit_code, preferred_timed_out)
        summary["backup_stop_reason"] = classify_failure(backup_exit_code, backup_timed_out)

    write_json(summary_path, summary)
    print(summary_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
