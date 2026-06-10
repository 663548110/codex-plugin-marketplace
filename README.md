# Codex Plugin Marketplace

Codex-supported plugin marketplace for local agent plugins.

## Structure

```text
.
├── .agents/
│   └── plugins/
│       └── marketplace.json
└── plugins/
    ├── rdesign-cli/
    │   ├── .codex-plugin/
    │   │   └── plugin.json
    │   └── skills/
    │       └── rdesign-cli/
    │           └── SKILL.md
    └── dify-knowledge/
        ├── .codex-plugin/
        │   └── plugin.json
        ├── assets/
        │   ├── dify-logo.png
        │   └── dify-logo.svg
        ├── README.md
        └── skills/
            └── dify-kb-maintainer/
                ├── SKILL.md
                ├── references/
                └── scripts/
```

## Plugins

- `rdesign-cli`: read-only RDesign workflow skill extracted from
  `huanlongAI/hl-scene-design-system`.
- `dify-knowledge`: Dify Knowledge Base Service API skill and helper script for Codex.

`dify-knowledge` uses the Dify Service API. Create a key in Dify:

```text
Knowledge -> Service API -> API Key
```

Then either set environment variables:

```sh
export DIFY_API_KEY=dataset-...
export DIFY_BASE_URL=http://192.168.97.251:8080/v1
```

Or write a machine-local ignored config file:

```sh
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py configure \
  --api-key dataset-... \
  --base-url http://192.168.97.251:8080/v1
```

## Local Install

```bash
codex plugin marketplace add /Users/hujiewei/apps/codex-plugin-marketplace
```
