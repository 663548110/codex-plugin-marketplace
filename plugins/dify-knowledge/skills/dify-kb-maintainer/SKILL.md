---
name: dify-kb-maintainer
description: Maintain and troubleshoot Dify knowledge bases, datasets, documents, chunks, retrieval tests, knowledge pipelines, and local/self-hosted Dify Service API usage from Codex. Use when the task mentions Dify knowledge base, dataset, document indexing, hit testing, retrieval quality, Service API key, pipeline templates, Dify local stack startup/restart, or using Dify knowledge from Codex.
---

# Dify KB Maintainer

Use this skill for Dify Knowledge Base tasks from Codex.

## Baseline

- Prefer the official Dify Knowledge Service API under `/v1`.
- Dify Knowledge API calls use `Authorization: Bearer <api_key>`.
- This plugin includes the user's LAN-only Dify Service API endpoint and API key as the default fallback.
- Override order is: `--api-key`, `DIFY_API_KEY`, `scripts/config.local.json`, then the built-in LAN default.
- `scripts/config.local.json` is optional and ignored by Git.
- Create replacement keys in Dify UI: `Knowledge -> Service API -> API Key`.

Read `references/knowledge-api.md` for endpoint shape.
Read `references/local-stack.md` when starting or checking a local Docker Compose Dify stack.

## Fast Workflow

1. Confirm the API endpoint and key source when overriding defaults:
   ```sh
   test -n "$DIFY_API_KEY" && echo DIFY_API_KEY_SET || echo USING_PLUGIN_DEFAULT_KEY
   curl -sS -i --max-time 10 "${DIFY_BASE_URL:-http://192.168.97.251:8080/v1}/datasets" | sed -n '1,12p'
   ```
2. Use the bundled helper for repeatable calls:
   ```sh
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-datasets
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-documents <dataset_id>
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "query"
   ```
3. For Git project ingestion into `项目信息库`, first run dry-run and inspect JSON:
   ```sh
   python3 skills/dify-kb-maintainer/scripts/git_project_ingest.py \
     --mode dry_run \
     --repo-url <git_repo_url> \
     --repo-ref <branch_or_tag_or_sha> \
     --project-key <stable_project_key>
   ```
4. Use `--mode create` only after reviewing the seven generated cards. Use `--mode update` to create a new version without deleting old documents.
5. If running from outside this skill folder, use the absolute script path from the installed plugin cache or repository checkout.
6. For the first API key, use the Dify browser UI rather than direct database edits.
7. For workflow DSL generation, use a dedicated Dify workflow builder skill if one is installed.

## Safety

- Prefer read-only inspection before mutations.
- Confirm target IDs before delete, replacement, segment deletion, or metadata migration operations.
- Avoid changing Dify project source code when the user only asks to operate the knowledge base.
- Avoid direct database operations unless the user explicitly asks for database-level repair.
- Redact API keys in all output.
