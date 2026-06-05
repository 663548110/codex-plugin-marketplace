---
name: rdesign-cli
description: 在 hl-scene-design-system 中工作，需要快速获取设计系统 CLI、组件文档、组件源码、运行时示例、token-core 值或 PR 变更范围边界时使用。手动扫描 Flutter/UniApp 组件文件、token JSON、docs/design-system 或 PARITY-MATRIX.md 之前先触发。
---

# RDesign CLI

Use `rdesign-cli` as the first read-only lookup tool in `hl-scene-design-system`.
It reads repository truth and does not modify files.

## Repository Handling

- Do not search for the repository before running `rdesign-cli`.
- The installed `rdesign-cli` wrapper reads the bundled local data installed with the CLI.
- If `rdesign-cli` is not on PATH or points at a missing `/private/tmp` dist file, run `rdesign-cli doctor` from the CLI package or use `node tools/design-system-cli/dist/cli.js doctor`.
- Only ask to locate the repository if a command fails with `Cannot locate hl-scene-design-system repo root` or the bundled data is missing.

## Command Rules

- Use `rdesign-cli get-repo-summary` to orient on repo purpose, truth sources, gaps, and scopes.
- Use `rdesign-cli list-components` to discover component ids and runtime availability.
- Use `rdesign-cli get-component-info <id> --runtime flutter|uniapp` for metadata only.
- Use `rdesign-cli get-component-docs <id> --runtime flutter|uniapp` for documentation content.
- Use `rdesign-cli get-component-source <id> --runtime flutter|uniapp --summary` first for source roles and generated-file summaries; add `--full` only when complete generated source is required.
- Use `rdesign-cli get-component-example <id> --runtime flutter|uniapp` for runnable example source.
- Use `rdesign-cli get-token <theme-id> <token-path>` for token-core values. Token paths may be canonical or aliases such as `rd/bg-color/inverted`, `bg-color-inverted`, `bg.color.inverted`, or `bgColorInverted`.
- Use `rdesign-cli suggest-svg-usage --asset <path> --slot <hex> --token <token-path>` to produce App-side `pubspec.yaml`, asset constant, `RDIcon.svgAsset`, and `colorMap` guidance.
- Use `rdesign-cli validate-svg --asset <path> --slot <hex> --pubspec <path>` to check replaceable color slots, hard-coded colors, pubspec registration, and recommended naming.
- Use `rdesign-cli check-scope --files <changed-files.txt>` before proposing or reviewing PR scope.

## Icon Boundaries

- `RDIcons` is the built-in iconfont `IconData` constant namespace.
- Business SVG icons should use `RDIcon.svgAsset`.
- Multi-color SVG icons should use `colorMap` and token-backed colors.

## Runtime Separation

Component detail commands must always include `--runtime flutter` or `--runtime uniapp`.
Do not ask for mixed Flutter and UniApp detail unless the task is explicitly comparing runtimes.
For comparison, call the same command twice, once per runtime.

## Guardrails

- Treat `packages/token-core` as the token SSOT.
- Do not infer missing runtime implementation from docs alone.
- Respect `PARITY-MATRIX.md`; `required` and `partial` are not permission to implement.
- Do not generate business logic, private app API wrappers, auth flows, or runtime-private tokens.
