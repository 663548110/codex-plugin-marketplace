# Dify Knowledge

Codex plugin for operating Dify Knowledge Base through the official Service API.

This plugin bundles:

- `skills/dify-kb-maintainer/SKILL.md`: Codex workflow guidance for Dify knowledge base tasks.
- `skills/dify-kb-maintainer/scripts/dify_kb.py`: a standard-library Python helper for Dify Knowledge API calls.
- Reference notes for local stack checks and Dify Knowledge API endpoints.
- `assets/dify-logo.png`: square Dify logo asset with a white background, used as the plugin logo and composer icon.

## API Key

Create a key in Dify:

```text
Knowledge -> Service API -> API Key
```

Then either export it before running helper commands:

```sh
export DIFY_API_KEY=dataset-...
```

Or store it in the plugin-local ignored config file:

```sh
python3 skills/dify-kb-maintainer/scripts/dify_kb.py configure \
  --api-key dataset-... \
  --base-url http://192.168.97.251:8080/v1
```

## Commands

```sh
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py list-datasets
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py create-dataset "项目信息库" --indexing-technique economy
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py create-text-document <dataset_id> "项目说明" "项目内容..."
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py list-documents <dataset_id>
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "怎么启动这个项目？"
```

`config.local.json` is ignored by Git and should stay local to the machine.
