#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

DEFAULT_BASE_URL = "http://192.168.97.251:8080/v1"
EMBEDDED_API_KEY = "dataset-7zlCE5uXcCTzkxaLWa13jSEy"
LOCAL_CONFIG_NAME = "config.local.json"
DEFAULT_SEARCH_METHOD = "hybrid_search"
DEFAULT_TOP_K = 12
DEFAULT_EMBEDDING_PROVIDER = "langgenius/openai/openai"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_RERANKING_PROVIDER = os.environ.get("DIFY_RERANK_PROVIDER", "langgenius/voyage/voyage")
DEFAULT_RERANKING_MODEL = os.environ.get("DIFY_RERANK_MODEL", "rerank-2.5")
MAX_DIFY_QUERY_LENGTH = 240

PROJECT_MEMORY_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "project_memory_cards.json"
KNOWLEDGE_OVERVIEW_PROJECT_KEY = "__knowledge_overview__"


def _load_project_memory_schema() -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        payload = json.loads(PROJECT_MEMORY_SCHEMA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing project memory schema: {PROJECT_MEMORY_SCHEMA_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid project memory schema: {PROJECT_MEMORY_SCHEMA_PATH}: {exc}") from exc

    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise SystemExit(f"Invalid project memory schema: {PROJECT_MEMORY_SCHEMA_PATH}: cards must be a list")
    overview = payload.get("knowledge_overview")
    return overview if isinstance(overview, dict) else None, [card for card in cards if isinstance(card, dict)]


KNOWLEDGE_OVERVIEW_SPEC, PROJECT_MEMORY_CARD_SPECS = _load_project_memory_schema()


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _api_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{parse.urlencode(params)}"
    return url


def _script_config_path() -> Path:
    return Path(__file__).resolve().parent / LOCAL_CONFIG_NAME


def _user_config_path() -> Path:
    return Path.home() / ".config" / "dify-knowledge" / "config.json"


def _config_paths() -> list[Path]:
    configured_path = os.environ.get("DIFY_KB_CONFIG")
    if configured_path:
        return [Path(configured_path).expanduser()]
    return [_script_config_path(), _user_config_path()]


def _load_config() -> dict[str, Any]:
    for path in _config_paths():
        if not path.is_file():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid Dify config JSON: {path}: {exc}") from exc
        if not isinstance(config, dict):
            raise SystemExit(f"Invalid Dify config JSON: {path}: root must be an object")
        config["_path"] = str(path)
        return config
    return {}


def _api_key(args: argparse.Namespace) -> str:
    config = getattr(args, "config", {}) or {}
    key = args.api_key or os.environ.get("DIFY_API_KEY") or config.get("api_key") or EMBEDDED_API_KEY
    if not key:
        raise SystemExit(
            "Missing API key. Set DIFY_API_KEY or pass --api-key. "
            "Or run `dify_kb.py configure --api-key ...`. "
            "Create keys in Dify: Knowledge -> Service API -> API Key."
        )
    return key


def _request_json(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    key = _api_key(args)
    url = _api_url(args.base_url, path, params)
    body = None
    headers = {"Authorization": f"Bearer {key}"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(
            f"{method} {url} failed: HTTP {exc.code}. key={_redact(key)}\n{detail}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except error.URLError as exc:
        print(f"{method} {url} failed: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _print(value: Any) -> None:
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parse_json_object(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError("JSON value must be an object")
    return data


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----dify-kb-{uuid.uuid4().hex}"
    lines: list[bytes] = []

    for name, value in fields.items():
        lines.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    lines.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(lines), boundary


def _cmd_configure(args: argparse.Namespace) -> Any:
    path = Path(args.config_path).expanduser() if args.config_path else _script_config_path()
    config: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid existing config JSON: {path}: {exc}") from exc
        if isinstance(current, dict):
            config.update(current)

    if args.local_api_key:
        config["api_key"] = args.local_api_key
    if args.local_base_url:
        config["base_url"] = args.local_base_url

    if not config.get("api_key"):
        raise SystemExit("Missing --api-key for local config.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return {
        "config_path": str(path),
        "base_url": config.get("base_url", DEFAULT_BASE_URL),
        "api_key": _redact(str(config["api_key"])),
    }


def _cmd_list_datasets(args: argparse.Namespace) -> Any:
    return _request_json(args, "GET", "/datasets", params={"page": args.page, "limit": args.limit})


def _cmd_create_dataset(args: argparse.Namespace) -> Any:
    payload: dict[str, Any] = {"name": args.name}
    if args.description:
        payload["description"] = args.description
    if args.indexing_technique:
        payload["indexing_technique"] = args.indexing_technique
    return _request_json(args, "POST", "/datasets", payload=payload)


def _cmd_list_documents(args: argparse.Namespace) -> Any:
    params: dict[str, Any] = {"page": args.page, "limit": args.limit}
    if args.keyword:
        params["keyword"] = args.keyword
    if args.indexing_status:
        params["indexing_status"] = args.indexing_status
    return _request_json(args, "GET", f"/datasets/{args.dataset_id}/documents", params=params)


def _cmd_get_document(args: argparse.Namespace) -> Any:
    return _request_json(args, "GET", f"/datasets/{args.dataset_id}/documents/{args.document_id}")


def _cmd_indexing_status(args: argparse.Namespace) -> Any:
    return _request_json(
        args,
        "GET",
        f"/datasets/{args.dataset_id}/documents/{args.document_id}/indexing-status",
    )


def _cmd_create_text_document(args: argparse.Namespace) -> Any:
    payload = {
        "name": args.name,
        "text": args.text,
        "indexing_technique": args.indexing_technique,
        "doc_form": args.doc_form,
        "doc_language": args.doc_language,
        "process_rule": args.process_rule,
    }
    return _request_json(args, "POST", f"/datasets/{args.dataset_id}/document/create-by-text", payload=payload)


def _infer_project_memory_topic(query: str) -> dict[str, Any] | None:
    normalized = query.lower()
    if _looks_like_environment_query(normalized):
        return _project_memory_card_spec("environment")
    if _looks_like_endpoint_index_query(normalized):
        return _project_memory_card_spec("endpoint_index")

    best: tuple[int, int, dict[str, Any] | None] = (0, 0, None)
    for index, topic in enumerate(PROJECT_MEMORY_CARD_SPECS):
        score = 0
        for term in topic["intent_signals"]:
            term_normalized = str(term).lower()
            if term_normalized in normalized:
                score += 3 if len(term_normalized) > 2 else 1
        if score > best[0]:
            best = (score, -index, topic)
    return best[2] if best[0] > 0 else None


def _infer_knowledge_overview_topic(query: str) -> dict[str, Any] | None:
    if not KNOWLEDGE_OVERVIEW_SPEC:
        return None

    normalized = query.lower()
    global_phrases = (
        "知识库",
        "有哪些项目",
        "有哪些仓库",
        "项目列表",
        "仓库列表",
        "项目索引",
        "项目之间",
        "仓库之间",
        "这些项目",
        "这些仓库",
        "跨仓库",
        "关联仓库",
        "先查哪个",
        "应该先查",
        "涉及哪些仓库",
        "涉及哪些项目",
    )
    relation_phrases = ("关系", "关联", "依赖", "边界", "负责")
    if any(phrase in normalized for phrase in global_phrases):
        return KNOWLEDGE_OVERVIEW_SPEC
    if ("项目" in normalized or "仓库" in normalized) and any(phrase in normalized for phrase in relation_phrases):
        return KNOWLEDGE_OVERVIEW_SPEC
    return None


def _project_memory_card_spec(card_id: str) -> dict[str, Any] | None:
    return next((spec for spec in PROJECT_MEMORY_CARD_SPECS if spec["id"] == card_id), None)


def _looks_like_environment_query(normalized_query: str) -> bool:
    environment_terms = ("api_base_url", "baseurl", "base url", "域名", "envkey", "appid", "brand", "manifest", "常量")
    environment_count = sum(1 for term in environment_terms if term in normalized_query)
    has_env_series = bool(re.search(r"\bdev\b.*\btest\b.*\bprod\b|\btest\b.*\bprod\b", normalized_query))
    return environment_count >= 1 and ("环境" in normalized_query or "env" in normalized_query or has_env_series)


def _looks_like_endpoint_index_query(normalized_query: str) -> bool:
    reverse_terms = ("接口名", "反查", "哪个页面调用", "调用链")
    endpoint_terms = ("endpoint", "path", "method", "接口")
    return any(term in normalized_query for term in reverse_terms) and any(
        term in normalized_query for term in endpoint_terms
    )


def _expand_project_memory_query(query: str, project_key: str | None) -> tuple[str, dict[str, Any] | None]:
    if project_key == KNOWLEDGE_OVERVIEW_PROJECT_KEY:
        topic = KNOWLEDGE_OVERVIEW_SPEC
        if not topic:
            return query, None
        expansion = str(topic["expansion"])
        parts = [query]
        for token in expansion.split():
            candidate = " ".join([*parts, token]).strip()
            if len(candidate) > MAX_DIFY_QUERY_LENGTH:
                break
            parts.append(token)
        return " ".join(" ".join(parts).split()), topic

    if not project_key:
        topic = _infer_knowledge_overview_topic(query)
        if not topic:
            return query, None
        expansion = str(topic["expansion"])
        parts = [query]
        for token in expansion.split():
            candidate = " ".join([*parts, token]).strip()
            if len(candidate) > MAX_DIFY_QUERY_LENGTH:
                break
            parts.append(token)
        return " ".join(" ".join(parts).split()), topic

    topic = _infer_project_memory_topic(query)
    if not topic:
        return query, None

    expansion = str(topic["expansion"])
    parts = [project_key, query]
    for token in expansion.split():
        candidate = " ".join([*parts, token]).strip()
        if len(candidate) > MAX_DIFY_QUERY_LENGTH:
            break
        parts.append(token)
    return " ".join(" ".join(parts).split()), topic


def _apply_weighted_score(payload: dict[str, Any], args: argparse.Namespace) -> None:
    retrieval_model = payload["retrieval_model"]
    if args.search_method != "hybrid_search" or args.no_weighted_score:
        retrieval_model["reranking_enable"] = bool(args.reranking_enable)
        retrieval_model["reranking_model"] = (
            {
                "reranking_provider_name": args.reranking_provider_name,
                "reranking_model_name": args.reranking_model_name,
            }
            if args.reranking_enable and args.reranking_provider_name and args.reranking_model_name
            else None
        )
        retrieval_model["reranking_mode"] = "reranking_model" if retrieval_model["reranking_model"] else None
        return

    retrieval_model["reranking_enable"] = True
    if args.reranking_provider_name and args.reranking_model_name:
        retrieval_model["reranking_model"] = {
            "reranking_provider_name": args.reranking_provider_name,
            "reranking_model_name": args.reranking_model_name,
        }
        retrieval_model["reranking_mode"] = "reranking_model"
    else:
        retrieval_model["reranking_model"] = {"reranking_provider_name": "", "reranking_model_name": ""}
        retrieval_model["reranking_mode"] = "weighted_score"
    retrieval_model["weights"] = {
        "vector_setting": {
            "vector_weight": args.vector_weight,
            "embedding_provider_name": args.embedding_provider_name,
            "embedding_model_name": args.embedding_model_name,
        },
        "keyword_setting": {"keyword_weight": args.keyword_weight},
    }


def _project_memory_record_score(record: dict[str, Any], topic: dict[str, Any], original_index: int) -> tuple[int, float, int]:
    segment = record.get("segment") or {}
    content = str(segment.get("content") or "")
    position = segment.get("position")
    boost = 0
    if position == topic["position"]:
        boost += 1000
    if str(topic["expansion"]).split()[0] in content:
        boost += 20
    return boost, float(record.get("score") or 0), -original_index


def _boost_project_memory_records(response: Any, topic: dict[str, Any] | None) -> Any:
    if not topic or not isinstance(response, dict):
        return response
    records = response.get("records")
    if not isinstance(records, list) or len(records) < 2:
        return response

    raw_top_positions = [record.get("segment", {}).get("position") for record in records[:10]]
    raw_top_scores = [record.get("score") for record in records[:10]]
    indexed_records = [(index, record) for index, record in enumerate(records)]
    indexed_records.sort(
        key=lambda item: _project_memory_record_score(item[1], topic, item[0]),
        reverse=True,
    )
    response["records"] = [record for _, record in indexed_records]
    response["client_retrieval"] = {
        "project_memory_topic": topic["id"],
        "preferred_segment_position": topic["position"],
        "client_reranked": True,
        "raw_top_positions": raw_top_positions,
        "raw_top_scores": raw_top_scores,
    }
    return response


def _cmd_retrieve(args: argparse.Namespace) -> Any:
    query, project_memory_topic = _expand_project_memory_query(args.query, args.project_key)
    payload: dict[str, Any] = {
        "query": query,
        "retrieval_model": {
            "search_method": args.search_method,
            "top_k": args.top_k,
            "score_threshold_enabled": args.score_threshold is not None,
        },
    }
    _apply_weighted_score(payload, args)
    metadata_project_key = args.project_key
    if not metadata_project_key and project_memory_topic and project_memory_topic.get("id") == "knowledge_overview":
        metadata_project_key = KNOWLEDGE_OVERVIEW_PROJECT_KEY
    if metadata_project_key:
        payload["retrieval_model"]["metadata_filtering_conditions"] = {
            "logical_operator": "and",
            "conditions": [
                {
                    "name": "project_key",
                    "comparison_operator": "is",
                    "value": metadata_project_key,
                }
            ],
        }
    if args.score_threshold is not None:
        payload["retrieval_model"]["score_threshold"] = args.score_threshold
    response = _request_json(args, "POST", f"/datasets/{args.dataset_id}/retrieve", payload=payload)
    if (
        payload["retrieval_model"].get("reranking_mode") == "reranking_model"
        and isinstance(response, dict)
        and not response.get("records")
    ):
        fallback_payload = json.loads(json.dumps(payload))
        fallback_model = fallback_payload["retrieval_model"]
        fallback_model["reranking_model"] = {"reranking_provider_name": "", "reranking_model_name": ""}
        fallback_model["reranking_mode"] = "weighted_score"
        response = _request_json(args, "POST", f"/datasets/{args.dataset_id}/retrieve", payload=fallback_payload)
    return _boost_project_memory_records(response, project_memory_topic)


def _cmd_upload_file(args: argparse.Namespace) -> Any:
    key = _api_key(args)
    file_path = Path(args.file).expanduser()
    if not file_path.is_file():
        raise SystemExit(f"File not found: {file_path}")

    body, boundary = _multipart_body({"data": json.dumps(args.data, ensure_ascii=False)}, "file", file_path)
    url = _api_url(args.base_url, f"/datasets/{args.dataset_id}/document/create-by-file")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"POST {url} failed: HTTP {exc.code}. key={_redact(key)}\n{detail}", file=sys.stderr)
        raise SystemExit(1) from exc
    return json.loads(raw) if raw else None


def _build_parser() -> argparse.ArgumentParser:
    config = _load_config()
    default_base_url = os.environ.get("DIFY_BASE_URL") or config.get("base_url") or DEFAULT_BASE_URL
    parser = argparse.ArgumentParser(description="Dify Knowledge Service API helper.")
    parser.add_argument("--base-url", default=default_base_url)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.set_defaults(config=config)
    sub = parser.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure", help="Store local API settings in an ignored config file.")
    configure.add_argument("--api-key", dest="local_api_key", required=True)
    configure.add_argument("--base-url", dest="local_base_url", default=default_base_url)
    configure.add_argument(
        "--config-path",
        default=None,
        help=f"Defaults to the script-local {LOCAL_CONFIG_NAME}.",
    )
    configure.set_defaults(func=_cmd_configure)

    list_datasets = sub.add_parser("list-datasets", help="List knowledge bases.")
    list_datasets.add_argument("--page", type=int, default=1)
    list_datasets.add_argument("--limit", type=int, default=20)
    list_datasets.set_defaults(func=_cmd_list_datasets)

    create_dataset = sub.add_parser("create-dataset", help="Create an empty knowledge base.")
    create_dataset.add_argument("name")
    create_dataset.add_argument("--description", default=None)
    create_dataset.add_argument("--indexing-technique", default="economy")
    create_dataset.set_defaults(func=_cmd_create_dataset)

    list_documents = sub.add_parser("list-documents", help="List documents in a knowledge base.")
    list_documents.add_argument("dataset_id")
    list_documents.add_argument("--page", type=int, default=1)
    list_documents.add_argument("--limit", type=int, default=20)
    list_documents.add_argument("--keyword", default=None)
    list_documents.add_argument("--indexing-status", default=None)
    list_documents.set_defaults(func=_cmd_list_documents)

    get_document = sub.add_parser("get-document", help="Get a document by ID.")
    get_document.add_argument("dataset_id")
    get_document.add_argument("document_id")
    get_document.set_defaults(func=_cmd_get_document)

    indexing_status = sub.add_parser("indexing-status", help="Get document indexing status.")
    indexing_status.add_argument("dataset_id")
    indexing_status.add_argument("document_id")
    indexing_status.set_defaults(func=_cmd_indexing_status)

    create_text = sub.add_parser("create-text-document", help="Create a document from inline text.")
    create_text.add_argument("dataset_id")
    create_text.add_argument("name")
    create_text.add_argument("text")
    create_text.add_argument("--indexing-technique", default="economy")
    create_text.add_argument("--doc-form", default="text_model")
    create_text.add_argument("--doc-language", default="Chinese")
    create_text.add_argument(
        "--process-rule-json",
        dest="process_rule",
        type=_parse_json_object,
        default={"mode": "automatic"},
        help="JSON object for process_rule.",
    )
    create_text.set_defaults(func=_cmd_create_text_document)

    retrieve = sub.add_parser("retrieve", help="Run retrieval against a knowledge base.")
    retrieve.add_argument("dataset_id")
    retrieve.add_argument("query")
    retrieve.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    retrieve.add_argument(
        "--search-method",
        choices=("hybrid_search", "semantic_search", "full_text_search", "keyword_search"),
        default=DEFAULT_SEARCH_METHOD,
    )
    retrieve.add_argument(
        "--no-weighted-score",
        action="store_true",
        help="Disable weighted-score hybrid retrieval. Useful for raw Dify debugging.",
    )
    retrieve.add_argument("--vector-weight", type=float, default=0.5)
    retrieve.add_argument("--keyword-weight", type=float, default=0.5)
    retrieve.add_argument("--embedding-provider-name", default=DEFAULT_EMBEDDING_PROVIDER)
    retrieve.add_argument("--embedding-model-name", default=DEFAULT_EMBEDDING_MODEL)
    retrieve.add_argument("--reranking-provider-name", default=DEFAULT_RERANKING_PROVIDER)
    retrieve.add_argument("--reranking-model-name", default=DEFAULT_RERANKING_MODEL)
    retrieve.add_argument(
        "--project-key",
        default=None,
        help="Filter retrieval results to documents tagged with doc_metadata.project_key.",
    )
    retrieve.add_argument("--reranking-enable", action="store_true")
    retrieve.add_argument("--score-threshold", type=float, default=None)
    retrieve.set_defaults(func=_cmd_retrieve)

    upload_file = sub.add_parser("upload-file", help="Upload a file as a document.")
    upload_file.add_argument("dataset_id")
    upload_file.add_argument("file")
    upload_file.add_argument(
        "--data-json",
        dest="data",
        type=_parse_json_object,
        default={
            "indexing_technique": "economy",
            "doc_form": "text_model",
            "doc_language": "Chinese",
            "process_rule": {"mode": "automatic"},
        },
        help="JSON object for the Dify create-by-file data field.",
    )
    upload_file.set_defaults(func=_cmd_upload_file)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _print(args.func(args))


if __name__ == "__main__":
    main()
