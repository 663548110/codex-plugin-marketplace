---
name: dify-kb-maintainer
description: Maintain and troubleshoot Dify knowledge bases, datasets, documents, chunks, retrieval tests, knowledge pipelines, and local/self-hosted Dify Service API usage from Codex. Use when the task mentions Dify knowledge base, dataset, document indexing, hit testing, retrieval quality, Service API key, pipeline templates, Dify local stack startup/restart, or using Dify knowledge from Codex.
---

# Dify KB Maintainer

Use this skill for Dify Knowledge Base tasks from Codex.

## Baseline

- Prefer the official Dify Knowledge Service API under `/v1`.
- Dify Knowledge API calls need `Authorization: Bearer $DIFY_API_KEY`.
- Do not store API keys in a repo, plugin, skill, or README.
- Create keys in Dify UI: `Knowledge -> Service API -> API Key`.
- For local self-hosted Dify, `DIFY_BASE_URL` is usually something like `http://<host>:8080/v1`.

Read `references/knowledge-api.md` for endpoint shape.
Read `references/local-stack.md` when starting or checking a local Docker Compose Dify stack.

## Fast Workflow

1. Confirm the API endpoint and key source:
   ```sh
   test -n "$DIFY_API_KEY" && echo DIFY_API_KEY_SET || echo DIFY_API_KEY_MISSING
   curl -sS -i --max-time 10 "${DIFY_BASE_URL:-http://192.168.97.251:8080/v1}/datasets" | sed -n '1,12p'
   ```
2. Use the bundled helper for repeatable calls:
   ```sh
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-datasets
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-documents <dataset_id>
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "query"
   ```
3. If running from outside this skill folder, use the absolute script path from the installed plugin cache or repository checkout.
4. For the first API key, use the Dify browser UI rather than direct database edits.
5. For workflow DSL generation, use a dedicated Dify workflow builder skill if one is installed.

## Safety

- Prefer read-only inspection before mutations.
- Confirm target IDs before delete, replacement, segment deletion, or metadata migration operations.
- Avoid changing Dify project source code when the user only asks to operate the knowledge base.
- Avoid direct database operations unless the user explicitly asks for database-level repair.
- Redact API keys in all output.
