# Agent Skills

A small collection of agent skills for Codex-style workflows.

## Development

- **review-fix-loop** — Run a real Codex review, fix important findings, rerun review, and stop when the patch is clean enough or the loop stops converging.

  ```bash
  npx skills@latest add ViaxCo/skills/review-fix-loop
  ```

  Includes a small helper script to extract the real reviewer result from `codex exec review --json`.
