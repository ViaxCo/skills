---
name: review-fix-loop
description: Run a local-first Codex review closeout loop: choose the right diff, use a separate Codex reviewer, fix important in-scope findings, validate narrowly, and rerun review until the patch is ready to close out or no longer converging cleanly. Use when the user wants an iterative Codex review/fix/review workflow for uncommitted work, branch diffs, or committed changes before finishing, committing, or shipping.
---

# Review Fix Loop

Use this skill to run a real review -> fix -> review closeout loop.

Prefer uncommitted local work first, but choose branch or commit review when the actual work state requires it.

## Contract

- Use a real separate reviewer run. Do not replace reviewer failure with self-review.
- Prefer `codex exec review --json` as the reviewer engine.
- Allow `codex review` only as a declared backup reviewer after terminal reviewer failure.
- Treat temporary silence during review as normal.
- Continue until no `fix now` findings remain, or the loop is no longer converging usefully.
- Reject speculative, noisy, low-confidence, or overly invasive findings.
- Prefer small fixes at the correct ownership boundary.
- Run focused proof after meaningful fix batches.
- Stay silent by default. Surface assumptions or blockers only when they materially affect trust, scope, or safety.

## Defaults

- Default scope: local uncommitted changes
- Default reviewer wait window: `15m`
- Soft convergence checkpoint: `8` passes
- Validation style: focused-first with conservative auto-detection
- Subagents: optional, only when they clearly reduce review noise or context load

## Scope Policy

Choose the real work state instead of forcing one mode:

- dirty local work: `--uncommitted`
- branch or PR work: `--base <base>`
- committed single change: `--commit <sha>`

Use [scripts/run_review.py](./scripts/run_review.py) for default scope auto-selection and reviewer execution.

If the scope is materially ambiguous, surface that once. Otherwise, start the loop and report at the end.

## Loop

1. Choose the review scope.
2. Run the reviewer with `python3 scripts/run_review.py --output-dir <dir>`.
3. Wait patiently. Silence is not failure on its own.
4. Read the structured summary from `run_review.py`.
5. If the preferred reviewer ended in terminal failure and the helper used the backup reviewer, continue with the backup review result. If both reviewer paths failed, stop and report that clearly.
6. Parse the authoritative review text with `python3 scripts/extract_review_output.py --summary <summary.json>`.
7. Triage findings into:
   - `fix now`: correctness, regressions, broken tests, missing critical error handling, security, data-loss risk, or other high-confidence issues in scope
   - `skip for now`: style-only, speculative, low-confidence, repeated low-value churn, out-of-scope findings, or fixes that require a broad refactor beyond scope
8. Fix only `fix now` findings.
9. Run the narrowest useful validation after each meaningful fix batch.
10. Repeat until a stop condition is reached.

## Triage Rules

Treat these as strong reasons to skip a finding unless context clearly raises the risk:

- unrealistic edge cases
- speculative risks
- broad rewrites
- low-confidence churn
- fixes that cross the ownership boundary without solving the current bug class

Prefer follow-up work over swelling the current patch.

If only skipped or out-of-scope findings remain after triage, stop with `no_fix_now_findings`.

## Convergence Rules

Use the `8`-pass checkpoint as a reassessment marker, not a hard cap.

Continue beyond the checkpoint only when the remaining findings are important, in scope, and the loop is still making meaningful progress.

Stop when any of these is true:

- `clean_review`
- `no_fix_now_findings`
- `not_converging`
- `scope_expansion`
- `reviewer_timeout`
- `reviewer_nonzero_exit`
- `missing_reviewer_output`
- `unconfirmed_final_batch`

If new findings start pulling unrelated subsystems into the patch, stop after the current batch and report `scope_expansion`.

Do not stop right after a fresh fix batch unless:

- a confirming review pass completed with usable output
- a real blocker prevented confirmation and you report it clearly
- the user explicitly told you to stop without another confirming review

## Validation

Prefer narrow proof tied to the fix.

Use conservative auto-detection when an obvious focused check exists. If no clear validation path exists, say so plainly in the final report instead of inventing broad or speculative checks.

Do not default to broad project checks unless they are clearly cheap, relevant, and unlikely to distract from the loop.

When findings touch auth, routing, app init, persistence, or financial calculations, run targeted scenario validation before deciding to stop.

## Optional Subagent

Use a subagent only when it clearly reduces noise or context load.

A subagent may:

- run the reviewer
- compress noisy review output into accepted findings, rejected findings, and validation targets

Do not require subagents for the loop to work.

## Helper

Run the helper like this:

```bash
tmp_dir=$(mktemp -d)
python3 scripts/run_review.py --output-dir "$tmp_dir"
```

The helper:

- chooses scope automatically by default
- runs `codex exec review --json` first
- falls back to `codex review` only after terminal reviewer failure
- writes a structured summary JSON
- writes the authoritative review text to a file path the summary reports

To inspect the authoritative review text:

```bash
python3 scripts/extract_review_output.py --summary "$tmp_dir/summary.json"
```

Use `python3 scripts/run_review.py --help` for optional flags such as explicit scope, base ref, commit ref, timeout, and disabling fallback.

## Final Report

Keep the final report compact. Include:

- scope used
- reviewer path used
- passes run
- findings fixed
- findings skipped, briefly why
- validation run
- final stop reason
- whether the final fix batch received a confirming review pass

Do not narrate every pass unless the user asks.
