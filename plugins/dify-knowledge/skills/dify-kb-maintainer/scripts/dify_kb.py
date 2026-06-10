#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

DEFAULT_BASE_URL = "http://192.168.97.251:8080/v1"


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _api_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{parse.urlencode(params)}"
    return url


def _api_key(args: argparse.Namespace) -> str:
    key = args.api_key or os.environ.get("DIFY_API_KEY")
    if not key:
        raise SystemExit(
            "Missing API key. Set DIFY_API_KEY or pass --api-key. "
            "Create it in Dify: Knowledge -> Service API -> API Key."
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


def _cmd_retrieve(args: argparse.Namespace) -> Any:
    payload: dict[str, Any] = {
        "query": args.query,
        "retrieval_model": {
            "search_method": args.search_method,
            "reranking_enable": args.reranking_enable,
            "reranking_model": None,
            "reranking_mode": None,
            "top_k": args.top_k,
            "score_threshold_enabled": args.score_threshold is not None,
        },
    }
    if args.score_threshold is not None:
        payload["retrieval_model"]["score_threshold"] = args.score_threshold
    return _request_json(args, "POST", f"/datasets/{args.dataset_id}/retrieve", payload=payload)


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
    parser = argparse.ArgumentParser(description="Dify Knowledge Service API helper.")
    parser.add_argument("--base-url", default=os.environ.get("DIFY_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    sub = parser.add_subparsers(dest="command", required=True)

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
    retrieve.add_argument("--top-k", type=int, default=3)
    retrieve.add_argument("--search-method", default="keyword_search")
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
