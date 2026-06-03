---
name: rdesign-cli
description: Use when working in hl-scene-design-system and needing fast, read-only facts about the design system CLI, component docs, component source, runtime examples, token-core values, or PR scope boundaries. Trigger before manually scanning Flutter/UniApp component files, token JSON, docs/design-system, or PARITY-MATRIX.md.
---

# RDesign CLI

Use `rdesign-cli` as the first read-only lookup tool in `hl-scene-design-system`.
It reads repository truth and does not modify files.

## Repository Handling

- Do not search for the repository before running `rdesign-cli`.
- The installed `rdesign-cli` wrapper reads the bundled local data installed with the CLI.
- If `rdesign-cli` is not on PATH, use it only after the user points you to the CLI package or the repository root.
- Only ask to locate the repository if a command fails with `Cannot locate hl-scene-design-system repo root` or the bundled data is missing.

## Command Rules

- Use `rdesign-cli get-repo-summary` to orient on repo purpose, truth sources, gaps, and scopes.
- Use `rdesign-cli list-components` to discover component ids and runtime availability.
- Use `rdesign-cli get-component-info <id> --runtime flutter|uniapp` for metadata only.
- Use `rdesign-cli get-component-docs <id> --runtime flutter|uniapp` for documentation content.
- Use `rdesign-cli get-component-source <id> --runtime flutter|uniapp` for implementation source.
- Use `rdesign-cli get-component-example <id> --runtime flutter|uniapp` for runnable example source.
- Use `rdesign-cli get-token <theme-id> <token-path>` for token-core values.
- Use `rdesign-cli check-scope --files <changed-files.txt>` before proposing or reviewing PR scope.

## Runtime Separation

Component detail commands must always include `--runtime flutter` or `--runtime uniapp`.
Do not ask for mixed Flutter and UniApp detail unless the task is explicitly comparing runtimes.
For comparison, call the same command twice, once per runtime.

## Guardrails

- Treat `packages/token-core` as the token SSOT.
- Do not infer missing runtime implementation from docs alone.
- Respect `PARITY-MATRIX.md`; `required` and `partial` are not permission to implement.
- Do not generate business logic, private app API wrappers, auth flows, or runtime-private tokens.
