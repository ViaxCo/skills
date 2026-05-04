---
name: review-fix-loop
description: "Use when the user wants an iterative review workflow: run a separate Codex reviewer, fix the important findings, rerun review, and stop when there are no important issues left or the loop reaches a sensible limit."
---

# Review Fix Loop

Use this skill for a real review -> fix -> real review loop with a separate Codex reviewer.

Use `codex exec review` as the review mechanism. Do not replace it with a local self-review. Do not modify this skill or its scripts during a run unless the user explicitly asks.

## Defaults

- scope: `--uncommitted`
- goal: continue until no `fix now` findings remain
- max review passes: `8` as a runaway guardrail, not the target
- stop policy: pragmatic convergence
- reviewer wait window: `15m`
- poll interval: `30s`
- validation: run the narrowest useful checks after each fix set when practical

Before starting, briefly list unresolved questions:

- scope: `--uncommitted`, `--base <branch>`, or `--commit <sha>`
- max review passes: `8` by default, or another cap if this task needs one
- stop policy: strict clean review vs pragmatic convergence
- scope boundaries for this conversation, if unclear
- reviewer wait window
- validation command, if any

If the user does not answer, continue with defaults.

## Loop

1. State assumptions.
2. Run a separate reviewer with `codex exec review --json`.
3. Wait patiently. Review runs can take several minutes. Poll for progress every `20-30s` instead of treating a short delay as failure.
4. Parse the reviewer result with [scripts/extract_review_output.py](scripts/extract_review_output.py).
   Accept either:
   - structured `exited_review_mode.review_output`
   - the final review `agent_message` text from `codex exec review --json`
5. If the reviewer times out, exits nonzero, or produces no final review message, stop and report that the real reviewer did not produce a usable result. Do not substitute a local review.
6. If there are no findings, stop.
7. Triage findings:
   - `fix now`: correctness, regressions, broken tests, missing error handling, security, data-loss, or high-confidence issues
   - `skip for now`: style-only, speculative, low-confidence, repeated low-value churn, out-of-scope findings, or fixes requiring a broad refactor beyond scope
8. Fix only `fix now` findings.
9. Run narrow validation if practical.
10. Repeat.
11. Stop when any of these is true:
   - no findings remain
   - no `fix now` findings remain
   - the next fix would be disproportionately invasive
   - the next fix would expand beyond the conversation's scope
   - the same kind of finding repeats after a reasonable fix attempt
   - the max review pass guardrail is reached

## Guardrails

- Default shape:
  - pass 1: review current changes
  - later passes: review after each fix batch until no `fix now` findings remain
  - max passes: `8` by default, used only to prevent runaway loops
- Do not stop immediately after applying a fresh fix batch unless one of these is true:
  - a confirming review pass ran and produced a usable result
  - a real blocker prevented confirmation and you report that clearly
  - the user explicitly told you to stop without a confirmation pass
- If the max pass guardrail is reached while `fix now` findings remain, stop and reassess instead of continuing automatically. Report that the patch is not converging cleanly.
- If new findings start touching behavior, ownership areas, files, or subsystems beyond what is needed for the current conversation's requested change, stop after the current batch and report `scope_expansion`. Examples: a dashboard task spilling into auth, routing, app init, payments, analytics, or shared providers.
- If only skipped or out-of-scope findings remain, stop immediately after triage and report `no_fix_now_findings`.
- Prefer follow-up work over endless loop churn. If the patch is growing materially, recommend splitting remaining fixes into a follow-up instead of continuing the same loop.
- When findings involve auth, routing, app init, mode persistence, or financial calculations, run targeted scenario validation before deciding to stop. Do not rely on review alone when those flows are in play.

Prefer small fix batches between review passes.

## Review Command

Preferred command:

```bash
tmp_jsonl=$(mktemp)
tmp_review=$(mktemp)
tmp_stderr=$(mktemp)
codex exec review --json --output-last-message "$tmp_review" --uncommitted > "$tmp_jsonl" 2> "$tmp_stderr"
```

Other scopes:

- `codex exec review --json --output-last-message "$tmp_review" --base main > "$tmp_jsonl" 2> "$tmp_stderr"`
- `codex exec review --json --output-last-message "$tmp_review" --commit <sha> > "$tmp_jsonl" 2> "$tmp_stderr"`

Capture stderr separately so unrelated CLI diagnostics, plugin warnings, analytics failures, or HTML challenge pages do not obscure the review loop. If the reviewer exits nonzero, times out, or produces no final review message, inspect and summarize `tmp_stderr` as part of the failure report. Do not treat stderr output alone as review findings when the reviewer succeeds and produces a usable final message.

Do not rely on stdin prompt form with `--uncommitted`; it can conflict with the CLI argument parsing. Prefer the plain review command above.

Do not add a custom local-review rubric. The purpose of this skill is to use the real review flow, with its built-in review behavior, as the source of findings.

Use this timing policy by default:

- allow up to `15m`
- poll every `30s`
- stop early only on explicit command failure

If the command finishes without a final reviewer message, treat that as reviewer failure and stop. Do not reinterpret that as a clean review.

## Parsing

Example:

```bash
tmp_jsonl=$(mktemp)
tmp_review=$(mktemp)
tmp_stderr=$(mktemp)
codex exec review --json --output-last-message "$tmp_review" --uncommitted > "$tmp_jsonl" 2> "$tmp_stderr"
python3 scripts/extract_review_output.py "$tmp_jsonl"
```

The parser accepts either structured `ExitedReviewMode.review_output` or the final `agent_message` text from the real reviewer. If the source is `agent_message`, use the review text itself as the authoritative result and extract findings from that text. Do not treat the absence of machine-parsed findings as a clean review unless the reviewer explicitly says there are no issues.

## Final Report

Report:

- passes run
- whether the final fix batch received a confirming review pass
- findings fixed
- findings intentionally skipped or treated as out of scope, with brief reasons
- validation performed
- whether a real reviewer result was obtained on each pass
- stop reason, for example: `clean_review`, `no_fix_now_findings`, `max_pass_guardrail`, `scope_expansion`, `reviewer_timeout`, `reviewer_nonzero_exit`, `missing_reviewer_message`, or `unconfirmed_final_batch`

Keep the final report compact. Do not narrate every pass in detail unless the user asks for it; summarize the loop outcome and only call out details that affect confidence or next steps.
