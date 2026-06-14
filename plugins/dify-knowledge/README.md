# Dify Knowledge

Codex plugin for operating Dify Knowledge Base through the official Service API.

This plugin bundles:

- `skills/dify-kb-maintainer/SKILL.md`: Codex workflow guidance for Dify knowledge base tasks.
- `skills/dify-kb-maintainer/scripts/dify_kb.py`: a standard-library Python helper for Dify Knowledge API calls.
- Reference notes for local stack checks and Dify Knowledge API endpoints.
- `assets/dify-logo.png`: square Dify logo asset with a white background, used as the plugin logo and composer icon.

## API Key

This plugin includes the default LAN-only Dify Knowledge Service API endpoint and API key for the local deployment:

```text
http://192.168.97.251:8080/v1
```

You can run helper commands directly when using that local Dify service.

To override the built-in key, create a key in Dify:

```text
Knowledge -> Service API -> API Key
```

Then either export it before running helper commands:

```sh
export DIFY_API_KEY=dataset-...
```

Or store an override in the plugin-local ignored config file:

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
python3 plugins/dify-knowledge/skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "这个项目怎么启动？" --project-key <project_key>
```

Retrieval defaults to hybrid search with `top_k=12` and Dify weighted-score reranking, which is a better fit for high-quality project-memory knowledge bases. When `--project-key` is provided, the helper adds project metadata filtering and schema-based project-card topic boosting so vague questions like "这个仓库大概什么结构？", "这个项目怎么启动？", or "接口地址在哪？" still land on the right card. The topic boost is based on the stable 9-card project-memory specification, not individual failed-query patches.

When no `--project-key` is provided and the question is about the knowledge base as a whole, such as "有哪些项目", "这些仓库什么关系", or "应该先查哪个项目", the helper routes to the unique knowledge-base overview document tagged with `project_key=__knowledge_overview__`. Pass `--search-method keyword_search` for economy-index smoke tests, or `--no-weighted-score` for raw debugging.

Key priority is: `--api-key`, `DIFY_API_KEY`, `config.local.json`, then the built-in LAN default.
