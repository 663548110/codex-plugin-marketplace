---
name: dify-kb-maintainer
description: Use Dify Knowledge from Codex for project context retrieval and knowledge-base maintenance. Use when the task mentions Dify knowledge bases, Agent 项目工作记忆库, project memory, project_key, datasets, documents, chunks, retrieval tests, pipelines, API keys, or local Dify stack operations.
---

# Dify KB Maintainer

Use this skill for Dify Knowledge Base tasks from Codex.

## When To Use

- Use this skill before opening source files when the user asks for project orientation, likely entry points, startup/build/test commands, environment/API base URLs, auth/permissions, routes/modules, request wrappers, business API modules, or maintenance conventions for an already-ingested project.
- Use it when the user asks Codex to "use Dify", "use the knowledge base", "retrieve project context", "test recall", "validate hit quality", or maintain Dify datasets/documents/chunks/pipelines.
- Use it for Dify local stack checks, Service API calls, metadata/document/indexing repair, and knowledge pipeline troubleshooting.
- Do not use it as the only authority for code-changing work. Treat recall as a map of where to look first, then verify against the repo when exact current implementation, line numbers, or behavior matters.

## Current Project Memory Boundary

The primary project-memory knowledge base is:

- Dify base URL: `http://192.168.97.251:8080/v1`
- Knowledge base: `Agent 项目工作记忆库`
- Dataset ID: `0c7535e8-128d-4d1a-9a66-15b1cad4d3da`
- Purpose: long-term working memory for Codex/agents, not a full source-code mirror.
- Reliable projects are the completed, enabled documents that have `doc_metadata.project_key`. Treat a project as unknown until `list-documents` or retrieval results confirm it is present and indexed.

This knowledge base is optimized for project-level recall. It should answer:

- what the project is and what business areas it covers
- how to start, build, test, or lint it
- where environment constants and API base URLs live
- how login, token handling, company/shop selection, and permissions are wired
- where routes, pages, layouts, and major business modules are organized
- where request wrappers, API source files, and business API modules are
- what maintenance rules, generated-file boundaries, and common pitfalls matter

Each healthy project document should be a parent-child high-quality document with 9 parent cards:

1. `项目卡：<project_key>`
2. `专题卡：<project_key> 启动构建测试`
3. `专题卡：<project_key> 权限与登录`
4. `专题卡：<project_key> 路由与业务模块`
5. `专题卡：<project_key> API 与请求处理`
6. `专题卡：<project_key> 业务 API 模块`
7. `专题卡：<project_key> 项目技能与维护约定`
8. `专题卡：<project_key> 环境配置与常量`
9. `专题卡：<project_key> 接口端点与关键文件索引`

Healthy documents should carry `doc_metadata.project_key`. When metadata filtering is unavailable in the helper command, include the project key in the query and verify the returned document/segment belongs to the intended project.

## Baseline

- Prefer the official Dify Knowledge Service API under `/v1`.
- Dify Knowledge API calls use `Authorization: Bearer <api_key>`.
- This plugin includes the user's LAN-only Dify Service API endpoint and API key as the default fallback.
- Override order is: `--api-key`, `DIFY_API_KEY`, `scripts/config.local.json`, then the built-in LAN default.
- `scripts/config.local.json` is optional and ignored by Git.
- Create replacement keys in Dify UI: `Knowledge -> Service API -> API Key`.

Read `references/knowledge-api.md` for endpoint shape.
Read `references/local-stack.md` when starting or checking a local Docker Compose Dify stack.

## Retrieval Workflow

1. Confirm the API endpoint and key source when overriding defaults:
   ```sh
   test -n "$DIFY_API_KEY" && echo DIFY_API_KEY_SET || echo USING_PLUGIN_DEFAULT_KEY
   curl -sS -i --max-time 10 "${DIFY_BASE_URL:-http://192.168.97.251:8080/v1}/datasets" | sed -n '1,12p'
   ```
2. Use the bundled helper for repeatable calls:
   ```sh
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-datasets
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py list-documents <dataset_id>
   python3 skills/dify-kb-maintainer/scripts/dify_kb.py retrieve <dataset_id> "query" --project-key <project_key>
   ```
3. The helper defaults to `hybrid_search` with `top_k=12` and weighted-score reranking, which matches the primary high-quality project-memory knowledge base. Use `--search-method keyword_search` only for economy-index smoke tests, and `--no-weighted-score` only for raw retrieval debugging.
4. For project-context questions, use natural queries and pass `--project-key <project_key>` whenever document metadata is available. The helper will filter by `doc_metadata.project_key`, expand the query with the matching project-memory card specification, and client-rerank the returned cards so similar projects and adjacent topics do not compete.
5. Good recall prompts should stay natural, for example `本地怎么跑起来`, `接口封装在哪里`, or `每个环境的接口地址是什么`. Avoid overfitting recall tests with too many exact table/field names unless debugging a specific miss.
6. Inspect returned records before answering: document name, segment position, content, score if present, and whether the content contains the intended project key.
7. In answers, state which project/card/segment the answer came from. If recall is weak, mixed across projects, stale, or missing, say so and either retry with a better query or verify in source code.
8. If running from outside this skill folder, use the absolute script path from the installed plugin cache or repository checkout.

## Maintenance Workflow

- For document health, check: completed/enabled document, `doc_metadata.project_key`, 9 parent segments, no `---CARD---` delimiter leaks, and retrieval hits for the major project topics above.
- Treat client-side project-card reranking as a consumption safeguard, not the source of truth. Long-term quality should come from schema-driven project cards that include `检索锚点` and `本卡回答范围` in each parent segment.
- For Dify workflow/pipeline repair, prefer Service API and UI operations first. Avoid direct database edits unless the user explicitly asks for database-level repair or there is no safer route.
- For the first API key or key replacement, use the Dify browser UI rather than direct database edits.
- For workflow DSL generation, use a dedicated Dify workflow builder skill if one is installed.

## Safety

- Prefer read-only inspection before mutations.
- Confirm target IDs before delete, replacement, segment deletion, or metadata migration operations.
- Avoid changing Dify project source code when the user only asks to operate the knowledge base.
- Avoid direct database operations unless the user explicitly asks for database-level repair.
- Redact API keys in all output.
- Do not treat knowledge-base recall as proof of latest source state after an unindexed PR, local edit, or branch switch. Use recall to save context, then verify source for exact implementation claims.
- Do not reveal secrets. The project-memory documents should name environment variables and source files, not credential values.
