# Dify Knowledge

Codex plugin for operating Dify Knowledge Base through the official Service API.

This plugin bundles:

- `skills/dify-kb-maintainer/SKILL.md`: Codex workflow guidance for Dify knowledge base tasks.
- `skills/dify-kb-maintainer/scripts/dify_kb.py`: a standard-library Python helper for Dify Knowledge API calls.
- Reference notes for local stack checks and Dify Knowledge API endpoints.
- `assets/dify-logo.svg`: Dify logo asset used as the plugin logo and composer icon.

## API Key

Create a key in Dify:

```text
Knowledge -> Service API -> API Key
```

Then export it before running helper commands:

```sh
export DIFY_API_KEY=dataset-...
```

Optional base URL:

```sh
export DIFY_BASE_URL=http://192.168.97.251:8080/v1
```

## Commands

```sh
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py list-datasets
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py create-dataset "项目信息库" --indexing-technique economy
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py create-text-document <dataset_id> "项目说明" "项目内容..."
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py list-documents <dataset_id>
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "怎么启动这个项目？"
```

The helper never stores API keys. Pass keys through `DIFY_API_KEY` or `--api-key`.
