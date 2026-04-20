---
name: review-fix-loop
description: "Use when the user wants an iterative review workflow: run a separate Codex reviewer, fix the important findings, rerun review, and stop when there are no important issues left or the loop reaches a sensible limit."
---

# Review Fix Loop

Use this skill for a real review -> fix -> real review loop with a separate Codex reviewer.

Use `codex exec review` as the review mechanism. Do not replace it with a local self-review. Do not modify this skill or its scripts during a run unless the user explicitly asks.

## Defaults

- scope: `--uncommitted`
- reviewed pass budget: `2`
- extra confirmation pass: `1` only if the latest fix batch has not yet been reviewed
- stop policy: pragmatic
- reviewer wait window: `15m`
- poll interval: `30s`
- validation: run the narrowest useful checks after each fix set when practical

Before starting, briefly list unresolved questions:

- scope: `--uncommitted`, `--base <branch>`, or `--commit <sha>`
- reviewed pass budget: `2` by default
- whether to allow the automatic confirmation pass
- stop policy: strict clean review vs pragmatic stop
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
   - `skip for now`: style-only, speculative, low-confidence, repeated low-value churn, or fixes requiring a broad refactor beyond scope
8. Fix only `fix now` findings.
9. Run narrow validation if practical.
10. Repeat.
11. Stop when any of these is true:
   - no findings remain
   - no `fix now` findings remain
   - the next fix would be disproportionately invasive
   - the reviewed pass budget is reached

## Guardrails

- Default shape:
  - pass 1: review current changes
  - pass 2: review after the first fix batch
  - pass 3: allowed only as a final confirmation pass when pass 2 caused another fix batch
- Do not continue into pass 4+ unless the user explicitly overrides the budget.
- Do not stop immediately after applying a fresh fix batch unless one of these is true:
  - a confirming review pass ran and produced a usable result
  - a real blocker prevented confirmation and you report that clearly
  - the user explicitly told you to stop without a confirmation pass
- If pass 3 still returns new `fix now` findings, stop the loop and reassess instead of continuing automatically. Report that the patch is not converging cleanly.
- If new findings start touching subsystems beyond the original task, stop after the current batch and report `scope_expansion`. Examples: a dashboard task spilling into auth, routing, app init, payments, analytics, or shared providers.
- Prefer follow-up work over endless loop churn. If the patch is growing materially, recommend splitting remaining fixes into a follow-up instead of continuing the same loop.
- When findings involve auth, routing, app init, mode persistence, or financial calculations, run targeted scenario validation before deciding to stop. Do not rely on review alone when those flows are in play.

Prefer small fix batches between review passes.

## Review Command

Preferred command:

```bash
tmp_jsonl=$(mktemp)
tmp_review=$(mktemp)
codex exec review --json --output-last-message "$tmp_review" --uncommitted > "$tmp_jsonl"
```

Other scopes:

- `codex exec review --json --output-last-message "$tmp_review" --base main > "$tmp_jsonl"`
- `codex exec review --json --output-last-message "$tmp_review" --commit <sha> > "$tmp_jsonl"`

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
codex exec review --json --output-last-message "$tmp_review" --uncommitted > "$tmp_jsonl"
python3 scripts/extract_review_output.py "$tmp_jsonl"
```

The parser accepts either structured `ExitedReviewMode.review_output` or the final `agent_message` text from the real reviewer. If the source is `agent_message`, use the review text itself as the authoritative result and extract findings from that text. Do not treat the absence of machine-parsed findings as a clean review unless the reviewer explicitly says there are no issues.

## Final Report

Report:

- passes run
- whether the final fix batch received a confirming review pass
- findings fixed
- findings intentionally skipped and why
- validation performed
- whether a real reviewer result was obtained on each pass
- stop reason, for example: `clean_review`, `no_fix_now_findings`, `pass_budget`, `scope_expansion`, `reviewer_timeout`, `reviewer_nonzero_exit`, `missing_reviewer_message`, or `unconfirmed_final_batch`
