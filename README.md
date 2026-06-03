# Codex Plugin Marketplace

Codex-supported plugin marketplace for local RDesign agent plugins.

## Structure

```text
.
├── .agents/
│   └── plugins/
│       └── marketplace.json
└── plugins/
    └── rdesign-cli/
        ├── .codex-plugin/
        │   └── plugin.json
        └── skills/
            └── rdesign-cli/
                └── SKILL.md
```

## Plugins

- `rdesign-cli`: read-only RDesign workflow skill extracted from
  `huanlongAI/hl-scene-design-system`.

The skill uses `rdesign-cli` for CLI lookups.

## Local Install

```bash
codex plugin marketplace add /Users/hujiewei/code/codex-plugin-marketplace
```
