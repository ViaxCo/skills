# Agent Skills

A small collection of agent skills for Codex-style workflows.

## Development

- **review-fix-loop** — Run a real Codex review, fix important findings, rerun review, and stop when the patch is clean enough or the loop stops converging.
  Includes a local-first review helper with structured-first parsing and backup `codex review` fallback.
  ```bash
  npx skills@latest add ViaxCo/skills/review-fix-loop
  ```
