#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback.
    tomllib = None  # type: ignore[assignment]

try:
    from dify_kb import DEFAULT_BASE_URL, EMBEDDED_API_KEY, _load_config, _redact
except ImportError:
    DEFAULT_BASE_URL = "http://192.168.97.251:8080/v1"
    EMBEDDED_API_KEY = ""

    def _load_config() -> dict[str, Any]:
        return {}

    def _redact(value: str) -> str:
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"


DEFAULT_DATASET_ID = "6ce6b122-0021-48bc-8c61-4336234e75e0"
VALID_MODES = {"dry_run", "create", "update"}
VALID_SCAN_DEPTHS = {"basic", "standard", "deep"}

SKIP_DIRS = {
    ".git",
    ".cache",
    ".next",
    ".nuxt",
    ".turbo",
    ".umi",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "Pods",
    "vendor",
}
SENSITIVE_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
SENSITIVE_EXTENSIONS = {".pem", ".key", ".crt", ".p12", ".pfx"}
SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".kt", ".dart", ".rs", ".php", ".rb"}
PRIORITY_PATTERNS = [
    "README.md",
    "README.zh-CN.md",
    "AGENTS.md",
    "CLAUDE.md",
    "package.json",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "package-lock.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "pubspec.yaml",
    "Cargo.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".github/workflows/*",
    ".gitlab-ci.yml",
    "config/config.ts",
    "config/routes.ts",
    "vite.config.*",
    "next.config.*",
    "src/app.tsx",
    "src/access.ts",
    "src/request*",
    "src/services/**",
    "src/router*",
    ".agents/skills/**/SKILL.md",
    ".claude/skills/**/SKILL.md",
]
SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|token|cookie|password|passwd|secret|private[_-]?key|authorization|session|access[_-]?key)"
    r"\s*[:=]\s*['\"]?[^'\"\s]{8,}"
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


@dataclass
class CloneResult:
    root: Path
    project_root: Path
    commit_sha: str
    remote_url: str


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def _today() -> str:
    return dt.datetime.now(dt.UTC).astimezone().date().isoformat()


def _strip_git_suffix(value: str) -> str:
    return value[:-4] if value.endswith(".git") else value


def _parse_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_commit_sha(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{7,40}", value))


def _validate_repo_url(repo_url: str) -> None:
    parsed = parse.urlparse(repo_url)
    if parsed.scheme in {"http", "https"}:
        if parsed.username or parsed.password:
            raise SystemExit("repo_url must not include credentials. Use environment credentials or Git credential helper.")
        if re.search(r"(?i)(token|password|secret|access_key|authorization)=", parsed.query):
            raise SystemExit("repo_url must not include tokens or secrets in query parameters.")


def _infer_project_key(repo_url: str, repo_subdir: str, explicit: str | None) -> str:
    if explicit:
        return explicit.strip().strip("/")

    repo = repo_url.strip()
    if repo.startswith("git@") and ":" in repo:
        repo = repo.split(":", 1)[1]
    else:
        parsed = parse.urlparse(repo)
        repo = parsed.path.lstrip("/") if parsed.scheme else repo

    repo = _strip_git_suffix(repo).strip("/")
    parts = [part for part in repo.split("/") if part]
    if len(parts) >= 2:
        key = "/".join(parts[-2:])
    elif parts:
        key = parts[-1]
    else:
        key = "unknown-project"

    clean_subdir = repo_subdir.strip("/")
    if clean_subdir:
        key = f"{key}/{clean_subdir}"
    return key


def _safe_subdir(repo_subdir: str) -> Path:
    if not repo_subdir:
        return Path()
    path = Path(repo_subdir)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise SystemExit("repo_subdir must be a relative path without '..'.")
    return path


def _clone_repo(repo_url: str, repo_ref: str, repo_subdir: str) -> CloneResult:
    _validate_repo_url(repo_url)
    temp_dir = Path(tempfile.mkdtemp(prefix="dify-git-project-"))
    repo_dir = temp_dir / "repo"
    shallow = ["git", "clone", "--depth=1", "--branch", repo_ref, repo_url, str(repo_dir)]
    result = _run(shallow)
    if result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if not _is_commit_sha(repo_ref):
            raise SystemExit(f"git shallow clone failed for ref {repo_ref}: {result.stderr.strip()}")
        temp_dir = Path(tempfile.mkdtemp(prefix="dify-git-project-"))
        repo_dir = temp_dir / "repo"
        clone = _run(["git", "clone", repo_url, str(repo_dir)])
        if clone.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise SystemExit(f"git clone failed: {clone.stderr.strip()}")
        checkout = _run(["git", "checkout", repo_ref], cwd=repo_dir)
        if checkout.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise SystemExit(f"git checkout failed for {repo_ref}: {checkout.stderr.strip()}")

    project_root = (repo_dir / _safe_subdir(repo_subdir)).resolve()
    if not project_root.exists() or not project_root.is_dir():
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise SystemExit(f"repo_subdir not found: {repo_subdir}")

    commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
    remote_url = _run(["git", "config", "--get", "remote.origin.url"], cwd=repo_dir).stdout.strip() or repo_url
    return CloneResult(root=repo_dir, project_root=project_root, commit_sha=commit_sha, remote_url=remote_url)


def _is_skipped(path: Path) -> bool:
    if path.name in SENSITIVE_FILE_NAMES or path.suffix in SENSITIVE_EXTENSIONS:
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _collect_files(root: Path, scan_depth: str) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in PRIORITY_PATTERNS:
        for path in root.glob(pattern):
            if path.is_file() and not _is_skipped(path):
                found[_relative(path, root)] = path

    if scan_depth in {"standard", "deep"}:
        max_files = 160 if scan_depth == "standard" else 420
        for path in root.rglob("*"):
            if len(found) >= max_files:
                break
            if not path.is_file() or _is_skipped(path):
                continue
            rel = _relative(path, root)
            if path.suffix not in SOURCE_EXTENSIONS:
                continue
            if (
                rel.startswith(("src/", "app/", "lib/", "internal/", "cmd/"))
                or any(marker in rel for marker in ("/services/", "/api/", "/routes/", "/router", "/pages/", "/app/"))
            ):
                found.setdefault(rel, path)

    return [found[key] for key in sorted(found)]


def _read_text(path: Path, max_bytes: int = 120_000) -> str:
    data = path.read_bytes()[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    return _sanitize_text(text)


def _sanitize_text(text: str) -> str:
    if PRIVATE_KEY_RE.search(text):
        return PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    lines: list[str] = []
    for line in text.splitlines():
        if SECRET_VALUE_RE.search(line):
            key = line.split("=", 1)[0].split(":", 1)[0].strip()
            lines.append(f"{key}: [REDACTED_SENSITIVE_VALUE]")
        else:
            lines.append(line)
    return "\n".join(lines)


def _load_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_toml(text: str) -> dict[str, Any]:
    if tomllib is None:
        return {}
    try:
        data = tomllib.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _first_meaningful_lines(text: str, limit: int = 5) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        clean = line.strip().strip("#").strip()
        if not clean or clean.startswith(("!", "[", "<")):
            continue
        result.append(clean)
        if len(result) >= limit:
            break
    return result


def _extract_strings(pattern: str, text: str, limit: int = 40) -> list[str]:
    seen: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        value = match.group(1).strip()
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def _add_unique(values: list[str], item: str | None) -> None:
    if item and item not in values:
        values.append(item)


def _empty_facts() -> dict[str, Any]:
    return {
        "project_key": "",
        "aliases": [],
        "repo_url": "",
        "repo_ref": "",
        "commit_sha": "",
        "repo_subdir": "",
        "verified_at": "",
        "tech_stack": [],
        "commands": {"install": "unknown", "dev": "unknown", "build": "unknown", "test": "unknown", "lint": "unknown"},
        "entry_files": [],
        "routes": [],
        "auth": {},
        "permissions": {},
        "api": {},
        "business_modules": [],
        "skills": [],
        "maintenance_rules": [],
        "source_files": [],
        "project_positioning": [],
        "ports": [],
        "env_vars": [],
        "ci_cd": [],
        "generated_boundaries": [],
    }


def _scan_repo(
    *,
    repo_url: str,
    repo_ref: str,
    repo_subdir: str,
    scan_depth: str,
    project_key: str | None,
    aliases: list[str],
    verified_at: str,
    context_pack: str | None,
) -> tuple[dict[str, Any], Path]:
    clone = _clone_repo(repo_url, repo_ref, repo_subdir)
    facts = _empty_facts()
    facts.update(
        {
            "project_key": _infer_project_key(repo_url, repo_subdir, project_key),
            "aliases": aliases,
            "repo_url": repo_url,
            "repo_ref": repo_ref,
            "repo_subdir": repo_subdir,
            "commit_sha": clone.commit_sha,
            "verified_at": verified_at,
        }
    )
    files = _collect_files(clone.project_root, scan_depth)
    facts["source_files"] = [_relative(path, clone.project_root) for path in files]
    _extract_repo_facts(facts, clone.project_root, files)
    if context_pack:
        facts["maintenance_rules"].append("补充上下文来自 context_pack；Git 扫描结果优先。")
        facts["project_positioning"].extend(_first_meaningful_lines(_sanitize_text(context_pack), 4))
    return facts, clone.root.parent


def _extract_repo_facts(facts: dict[str, Any], root: Path, files: list[Path]) -> None:
    by_rel = {_relative(path, root): path for path in files}
    commands = facts["commands"]
    api: dict[str, Any] = {"request_files": [], "service_files": [], "endpoint_prefixes": [], "base_url_or_proxy": []}
    auth: dict[str, Any] = {"login_entry": [], "current_user": [], "auth_storage": [], "token_header": [], "route_permission": []}
    permissions: dict[str, Any] = {"route_permission": [], "button_action_permission": [], "roles_fields": []}

    for rel, path in by_rel.items():
        text = _read_text(path)
        lower_rel = rel.lower()
        if rel in {"README.md", "README.zh-CN.md"}:
            facts["project_positioning"].extend(_first_meaningful_lines(text, 6))
        if rel in {"AGENTS.md", "CLAUDE.md"} or rel.endswith("/SKILL.md"):
            facts["maintenance_rules"].extend(_first_meaningful_lines(text, 8))
            if rel.endswith("/SKILL.md"):
                skill_name = Path(rel).parent.name
                facts["skills"].append({"name": skill_name, "file": rel})
        if rel == "package.json":
            data = _load_json(text)
            scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
            deps: dict[str, Any] = {}
            for dep_key in ("dependencies", "devDependencies"):
                value = data.get(dep_key)
                if isinstance(value, dict):
                    deps.update(value)
            _add_unique(facts["tech_stack"], "Node.js")
            for dep, label in (
                ("typescript", "TypeScript"),
                ("react", "React"),
                ("next", "Next.js"),
                ("vue", "Vue"),
                ("vite", "Vite"),
                ("umi", "Umi"),
                ("@umijs/max", "Umi Max"),
                ("antd", "Ant Design"),
                ("tailwindcss", "Tailwind CSS"),
                ("vitest", "Vitest"),
                ("jest", "Jest"),
                ("playwright", "Playwright"),
            ):
                if dep in deps:
                    _add_unique(facts["tech_stack"], label)
            package_manager = "npm"
            if "pnpm-lock.yaml" in by_rel:
                package_manager = "pnpm"
            elif "yarn.lock" in by_rel:
                package_manager = "yarn"
            commands["install"] = f"{package_manager} install"
            for key in ("dev", "start"):
                if key in scripts and commands["dev"] == "unknown":
                    commands["dev"] = f"{package_manager} {key}"
            for key in ("build", "test", "lint", "type-check", "typecheck"):
                if key in scripts:
                    slot = "lint" if key in {"lint", "type-check", "typecheck"} else key
                    if commands.get(slot) == "unknown":
                        commands[slot] = f"{package_manager} {key}"
        if rel == "pyproject.toml":
            data = _load_toml(text)
            _add_unique(facts["tech_stack"], "Python")
            project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
            if project.get("requires-python"):
                _add_unique(facts["tech_stack"], f"Python {project['requires-python']}")
            commands["install"] = commands["install"] if commands["install"] != "unknown" else "pip install -e ."
            commands["test"] = commands["test"] if commands["test"] != "unknown" else "pytest"
        if rel == "requirements.txt":
            _add_unique(facts["tech_stack"], "Python")
            commands["install"] = commands["install"] if commands["install"] != "unknown" else "pip install -r requirements.txt"
        if rel == "go.mod":
            _add_unique(facts["tech_stack"], "Go")
            module = re.search(r"(?m)^module\s+(.+)$", text)
            if module:
                _add_unique(facts["project_positioning"], f"Go module: {module.group(1).strip()}")
            commands["test"] = commands["test"] if commands["test"] != "unknown" else "go test ./..."
        if rel == "pubspec.yaml":
            _add_unique(facts["tech_stack"], "Flutter/Dart")
            commands["install"] = commands["install"] if commands["install"] != "unknown" else "flutter pub get"
            commands["dev"] = commands["dev"] if commands["dev"] != "unknown" else "flutter run"
            commands["test"] = commands["test"] if commands["test"] != "unknown" else "flutter test"
        if rel == "Cargo.toml":
            _add_unique(facts["tech_stack"], "Rust")
            commands["build"] = commands["build"] if commands["build"] != "unknown" else "cargo build"
            commands["test"] = commands["test"] if commands["test"] != "unknown" else "cargo test"
        if rel == "pom.xml" or rel.endswith("build.gradle"):
            _add_unique(facts["tech_stack"], "Java/JVM")
        if rel.startswith(".github/workflows/") or rel == ".gitlab-ci.yml":
            facts["ci_cd"].append(rel)
        if rel in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            _add_unique(facts["tech_stack"], "Docker")
            facts["ports"].extend(_extract_strings(r"(?:(?:ports|EXPOSE)[^\n]*?)(\d{2,5})", text, 12))
            facts["env_vars"].extend(_extract_strings(r"\b([A-Z][A-Z0-9_]{2,})\b", text, 40))
        if "vite.config" in lower_rel or "next.config" in lower_rel or lower_rel.endswith("config/config.ts"):
            facts["entry_files"].append(rel)
            api["base_url_or_proxy"].extend(_extract_strings(r"['\"](/api[^'\"]*|https?://[^'\"]+)['\"]", text, 20))
        if lower_rel.endswith(
            ("src/app.tsx", "src/main.tsx", "src/main.ts", "src/index.tsx", "src/index.ts", "app.py", "main.py", "cli.py")
        ):
            facts["entry_files"].append(rel)
        if "route" in lower_rel or "router" in lower_rel or "/pages/" in lower_rel or "/app/" in lower_rel:
            facts["routes"].extend(_extract_strings(r"(?:path|pathname)\s*:\s*['\"]([^'\"]+)['\"]", text, 60))
            facts["routes"].extend(_extract_strings(r"\.route\(\s*['\"]([^'\"]+)['\"]", text, 60))
            if "/pages/" in lower_rel or "/app/" in lower_rel:
                module = Path(rel).parts[1] if len(Path(rel).parts) > 2 and Path(rel).parts[0] in {"src", "app"} else Path(rel).parent.name
                _add_unique(facts["business_modules"], f"{module}: {rel}")
        if path.suffix in SOURCE_EXTENSIONS and rel.startswith(("src/", "app/", "lib/", "internal/", "cmd/")):
            parts = Path(rel).parts
            if len(parts) >= 2:
                module = parts[1] if parts[0] == "src" else parts[0]
                _add_unique(facts["business_modules"], f"{module}: {rel}")
        if "access" in lower_rel or "permission" in lower_rel:
            permissions["route_permission"].append(rel)
            auth["route_permission"].append(rel)
        if "login" in lower_rel:
            auth["login_entry"].append(rel)
        if "request" in lower_rel or "/services/" in lower_rel or "/api/" in lower_rel:
            if "request" in lower_rel:
                api["request_files"].append(rel)
            if "/services/" in lower_rel or "/api/" in lower_rel:
                api["service_files"].append(rel)
            api["endpoint_prefixes"].extend(_extract_strings(r"['\"](/[^'\"\s{}]+)['\"]", text, 80))
            if re.search(r"currentUser|current_user|/me\b|/user/info|/profile", text):
                auth["current_user"].append(rel)
            if re.search(r"localStorage|sessionStorage|cookie|Authorization|Bearer|X-Token|token", text):
                auth["token_header"].append(rel)
        if re.search(r"role|permission|authority|access", text, flags=re.IGNORECASE):
            permissions["roles_fields"].append(rel)
        if re.search(r"generated|openapi|swagger|do not edit|auto-generated", text, flags=re.IGNORECASE):
            facts["generated_boundaries"].append(rel)

    facts["api"] = {key: sorted(set(value)) for key, value in api.items()}
    facts["auth"] = {key: sorted(set(value)) for key, value in auth.items()}
    facts["permissions"] = {key: sorted(set(value)) for key, value in permissions.items()}
    facts["entry_files"] = sorted(set(facts["entry_files"]))
    facts["routes"] = sorted(set(facts["routes"]))[:80]
    facts["business_modules"] = sorted(set(facts["business_modules"]))[:80]
    facts["ports"] = sorted(set(facts["ports"]))
    facts["env_vars"] = [value for value in sorted(set(facts["env_vars"])) if not re.search(r"SECRET|TOKEN|PASSWORD|KEY", value)]
    facts["ci_cd"] = sorted(set(facts["ci_cd"]))
    facts["generated_boundaries"] = sorted(set(facts["generated_boundaries"]))


def _facts_from_context_pack(
    *,
    context_pack: str,
    repo_path: str | None,
    git_sha: str | None,
    repo_url: str | None,
    repo_ref: str,
    repo_subdir: str,
    project_key: str | None,
    aliases: list[str],
    verified_at: str,
) -> dict[str, Any]:
    text = _sanitize_text(context_pack)
    facts = _empty_facts()
    parsed = _load_json(text)
    if parsed:
        facts.update({key: value for key, value in parsed.items() if key in facts})
    facts.update(
        {
            "project_key": project_key or parsed.get("project_key") or "context-pack-project",
            "aliases": aliases or parsed.get("aliases", []),
            "repo_url": repo_url or parsed.get("repo_url", "unknown"),
            "repo_ref": repo_ref or parsed.get("repo_ref", "unknown"),
            "repo_subdir": repo_subdir or parsed.get("repo_subdir", ""),
            "commit_sha": git_sha or parsed.get("commit_sha", "unknown"),
            "verified_at": verified_at,
        }
    )
    facts["source_files"] = parsed.get("source_files", []) if parsed else ["context_pack"]
    if repo_path:
        facts["source_files"].append(f"repo_path: {repo_path}")
    if not parsed:
        facts["project_positioning"] = _first_meaningful_lines(text, 8)
        facts["maintenance_rules"].append("context_pack 未提供结构化 JSON；已按 Markdown/纯文本摘要提取。")
    if not git_sha:
        facts["maintenance_rules"].append("context_pack 缺少 git_sha，需要回到仓库复核。")
    if not repo_path:
        facts["maintenance_rules"].append("context_pack 缺少 repo_path，需要回到仓库复核。")
    return facts


def _fmt_list(values: list[Any], empty: str = "当前仓库扫描未发现明确实现，需要回到仓库复核。") -> str:
    clean = [str(value) for value in values if value]
    if not clean:
        return empty
    return "\n".join(f"- {value}" for value in clean)


def _fmt_dict(value: dict[str, Any]) -> str:
    rows: list[str] = []
    for key, item in value.items():
        if isinstance(item, list):
            rows.append(f"- {key}: {', '.join(str(v) for v in item) if item else '未发现'}")
        elif isinstance(item, dict):
            rows.append(f"- {key}: {json.dumps(item, ensure_ascii=False)}")
        else:
            rows.append(f"- {key}: {item if item else '未发现'}")
    return "\n".join(rows) if rows else "当前仓库扫描未发现明确实现，需要回到仓库复核。"


def _meta(facts: dict[str, Any], source_files: list[str]) -> str:
    return "\n".join(
        [
            f"项目标识：{facts['project_key']}",
            f"项目别名：{', '.join(facts['aliases']) if facts['aliases'] else '无'}",
            f"仓库地址：{facts['repo_url']}",
            f"仓库 ref：{facts['repo_ref']}",
            f"repo_subdir：{facts['repo_subdir'] or '无'}",
            f"核验提交：{facts['commit_sha']}",
            f"最后核验日期：{facts['verified_at']}",
            f"信息来源：{', '.join(source_files) if source_files else 'unknown'}",
        ]
    )


def _keywords(project_key: str, *extra: str) -> list[str]:
    base = [project_key, project_key.split("/")[-1], "项目信息库"]
    for item in extra:
        base.extend(part for part in item.split() if part)
    return list(dict.fromkeys(base))


def _doc(name: str, content: str, keywords: list[str], source_files: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "content": content.strip() + "\n",
        "retrieval_keywords": keywords,
        "source_files": source_files,
    }


def _generate_documents(facts: dict[str, Any]) -> list[dict[str, Any]]:
    project_key = facts["project_key"]
    source_files = facts["source_files"][:40]
    all_source = source_files or ["unknown"]
    docs: list[dict[str, Any]] = []

    project_content = f"""
# 项目卡：{project_key}

{_meta(facts, all_source)}

## {project_key} 项目定位

{project_key} 的项目定位依据仓库 README/说明文件提取：
{_fmt_list(facts["project_positioning"])}

## {project_key} 技术栈

{project_key} 的技术栈依据 manifest/config 文件提取：
{_fmt_list(facts["tech_stack"])}

## {project_key} 重要入口

{project_key} 的重要入口文件如下：
{_fmt_list(facts["entry_files"])}

## {project_key} 主要业务模块

{project_key} 的主要业务模块如下：
{_fmt_list(facts["business_modules"])}

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '项目定位 技术栈 入口 业务模块'))}
"""
    docs.append(_doc(f"项目卡：{project_key}", project_content, _keywords(project_key, "项目定位 技术栈 入口 业务模块"), all_source))

    commands = facts["commands"]
    startup_content = f"""
# 专题卡：{project_key} 启动构建测试

{_meta(facts, all_source)}

## {project_key} 版本与运行环境

{project_key} 的版本与运行环境依据依赖 manifest 提取：
{_fmt_list(facts["tech_stack"])}

## {project_key} 命令

{project_key} 的安装命令是：{commands.get("install", "unknown")}
{project_key} 的启动命令是：{commands.get("dev", "unknown")}
{project_key} 的构建命令是：{commands.get("build", "unknown")}
{project_key} 的测试命令是：{commands.get("test", "unknown")}
{project_key} 的 lint/typecheck 命令是：{commands.get("lint", "unknown")}

## {project_key} 端口与环境变量

{project_key} 的运行端口：
{_fmt_list(facts["ports"])}

{project_key} 的环境变量名只记录变量名，不记录敏感值：
{_fmt_list(facts["env_vars"])}

## {project_key} CI/CD

{project_key} 的 CI/CD 配置：
{_fmt_list(facts["ci_cd"])}

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '启动 构建 测试 lint typecheck 端口 环境变量'))}
"""
    docs.append(_doc(f"专题卡：{project_key} 启动构建测试", startup_content, _keywords(project_key, "启动 构建 测试 lint typecheck 端口 环境变量"), all_source))

    auth_content = f"""
# 专题卡：{project_key} 权限与登录

{_meta(facts, all_source)}

## {project_key} 登录入口

{project_key} 的登录入口：
{_fmt_list(facts["auth"].get("login_entry", []))}

## {project_key} current user/me 接口

{project_key} 的 current user/me 相关位置：
{_fmt_list(facts["auth"].get("current_user", []))}

## {project_key} auth storage 与 token/header

{project_key} 的 auth storage、token/header 相关位置只记录文件，不记录具体敏感值：
{_fmt_list(facts["auth"].get("token_header", []))}

## {project_key} route/button/action permission

{project_key} 的路由权限、按钮权限、角色权限字段：
{_fmt_dict(facts["permissions"])}

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '权限 登录 currentUser me access permissions role token header'))}
"""
    docs.append(_doc(f"专题卡：{project_key} 权限与登录", auth_content, _keywords(project_key, "权限 登录 currentUser me access permissions role token header"), all_source))

    route_content = f"""
# 专题卡：{project_key} 路由与业务模块

{_meta(facts, all_source)}

## {project_key} route/router 配置

{project_key} 的路由配置或路由路径：
{_fmt_list(facts["routes"])}

## {project_key} 默认入口和页面目录

{project_key} 的默认入口和页面目录：
{_fmt_list(facts["entry_files"] + [item for item in facts["source_files"] if "/pages/" in item or "/app/" in item][:20])}

## {project_key} 主要业务模块

{project_key} 的业务模块与对应文件：
{_fmt_list(facts["business_modules"])}

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '路由 router routes 页面入口 业务模块'))}
"""
    docs.append(_doc(f"专题卡：{project_key} 路由与业务模块", route_content, _keywords(project_key, "路由 router routes 页面入口 业务模块"), all_source))

    api_content = f"""
# 专题卡：{project_key} API 与请求处理

{_meta(facts, all_source)}

## {project_key} request 封装

{project_key} 的 request 封装位置：
{_fmt_list(facts["api"].get("request_files", []))}

## {project_key} baseURL/proxy

{project_key} 的 baseURL/proxy 线索：
{_fmt_list(facts["api"].get("base_url_or_proxy", []))}

## {project_key} service 目录和 API source of truth

{project_key} 的 service/API 文件：
{_fmt_list(facts["api"].get("service_files", [])[:80])}

## {project_key} response envelope/error/generated 边界

{project_key} 的生成代码边界：
{_fmt_list(facts["generated_boundaries"])}

{project_key} 当前仓库扫描未发现明确 response envelope 或 error handling 时，需要回到 request/service 封装复核。

## {project_key} 检索关键词

{', '.join(_keywords(project_key, 'API 请求封装 request baseURL proxy response error generated'))}
"""
    docs.append(_doc(f"专题卡：{project_key} API 与请求处理", api_content, _keywords(project_key, "API 请求封装 request baseURL proxy response error generated"), all_source))

    api_modules = facts["api"].get("service_files", [])
    endpoint_prefixes = facts["api"].get("endpoint_prefixes", [])[:80]
    business_api_content = f"""
# 专题卡：{project_key} 业务 API 模块

{_meta(facts, all_source)}

## {project_key} services 下的主要模块

{project_key} 的 services/API 模块：
{_fmt_list(api_modules[:100])}

## {project_key} endpoint 前缀

{project_key} 的 endpoint 前缀：
{_fmt_list(endpoint_prefixes)}

## {project_key} CRUD/分页归一化规则

{project_key} 当前仓库扫描未发现明确实现，需要回到仓库复核。

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '业务 API 模块 services endpoint CRUD 分页'))}
"""
    docs.append(_doc(f"专题卡：{project_key} 业务 API 模块", business_api_content, _keywords(project_key, "业务 API 模块 services endpoint CRUD 分页"), all_source))

    skill_content = f"""
# 专题卡：{project_key} 项目技能与维护约定

{_meta(facts, all_source)}

## {project_key} AGENTS/CLAUDE 规则

{project_key} 的维护约定：
{_fmt_list(facts["maintenance_rules"])}

## {project_key} .agents/.claude skills

{project_key} 的项目技能：
{_fmt_list([f"{item['name']}: {item['file']}" for item in facts["skills"]])}

## {project_key} 生成代码不要手改的边界

{project_key} 的生成代码边界：
{_fmt_list(facts["generated_boundaries"])}

## {project_key} commit/lint/test 要求

{project_key} 的 lint/test 要求见启动构建测试专题卡；未发现明确 commit 规则时，需要回到仓库复核。

## {project_key} 检索关键词

{', '.join(_keywords(project_key, '项目技能 维护约定 AGENTS CLAUDE generated lint test commit'))}
"""
    docs.append(_doc(f"专题卡：{project_key} 项目技能与维护约定", skill_content, _keywords(project_key, "项目技能 维护约定 AGENTS CLAUDE generated lint test commit"), all_source))
    return docs


def _quality_check(facts: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    required = ["项目标识：", "仓库地址：", "仓库 ref：", "核验提交：", "最后核验日期：", "信息来源：", "检索关键词"]
    for doc in documents:
        content = doc["content"]
        for marker in required:
            if marker not in content:
                missing.append(f"{doc['name']} missing {marker}")
        if facts["project_key"] not in content:
            missing.append(f"{doc['name']} missing project_key")
        if SECRET_VALUE_RE.search(content) or PRIVATE_KEY_RE.search(content):
            missing.append(f"{doc['name']} contains suspected sensitive value")
    if facts["commit_sha"] in {"", "unknown"}:
        warnings.append("commit_sha is unknown; retrieval cards should be reverified against the repository.")
    if not facts["source_files"]:
        warnings.append("source_files is empty.")
    return {"passed": not missing, "missing": missing, "warnings": warnings}


def _api_key(args: argparse.Namespace) -> str:
    config = _load_config()
    key = args.api_key or os.environ.get("DIFY_API_KEY") or config.get("api_key") or EMBEDDED_API_KEY
    if not key:
        raise SystemExit("Missing Dify API key. Set DIFY_API_KEY or configure the plugin.")
    return str(key)


def _api_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{parse.urlencode(params)}"
    return url


def _request_json(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    key = _api_key(args)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    url = _api_url(args.base_url, path, params)
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"{method} {url} failed: HTTP {exc.code}. key={_redact(key)}\n{detail}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _find_conflicts(args: argparse.Namespace, project_key: str) -> list[dict[str, Any]]:
    result = _request_json(
        args,
        "GET",
        f"/datasets/{args.dataset_id}/documents",
        params={"page": 1, "limit": 100, "keyword": project_key},
    )
    data = result.get("data", []) if isinstance(result, dict) else []
    return [item for item in data if project_key in str(item.get("name", ""))]


def _write_documents(args: argparse.Namespace, facts: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    if args.mode == "dry_run":
        return {"written": False, "document_ids": [], "conflicts": []}
    conflicts = _find_conflicts(args, facts["project_key"])
    if args.mode == "create" and conflicts:
        return {
            "written": False,
            "document_ids": [],
            "conflicts": [{"id": item.get("id"), "name": item.get("name")} for item in conflicts],
            "error": "conflict: existing documents found for project_key",
        }

    suffix = ""
    if args.mode == "update":
        short_sha = facts["commit_sha"][:8] if facts["commit_sha"] not in {"", "unknown"} else facts["verified_at"]
        suffix = f" @ {short_sha}"

    document_ids: list[str] = []
    for doc in documents:
        response = _request_json(
            args,
            "POST",
            f"/datasets/{args.dataset_id}/document/create-by-text",
            payload={
                "name": f"{doc['name']}{suffix}",
                "text": doc["content"],
                "indexing_technique": "economy",
                "doc_form": "text_model",
                "doc_language": "Chinese",
                "process_rule": {"mode": "automatic"},
            },
        )
        document = response.get("document", response) if isinstance(response, dict) else {}
        doc_id = document.get("id") if isinstance(document, dict) else None
        if doc_id:
            document_ids.append(doc_id)
    return {"written": True, "document_ids": document_ids, "conflicts": []}


def _retrieval_queries(project_key: str) -> list[str]:
    return [
        f"{project_key} 怎么启动 构建 测试",
        f"{project_key} 权限 currentUser access permissions",
        f"{project_key} API 来源 请求封装 后端响应",
        f"{project_key} 路由 业务模块 页面入口",
        f"{project_key} 业务 API 模块",
        f"{project_key} 项目技能 维护约定",
    ]


def _extract_hit_names(response: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(response, dict):
        return names
    records = response.get("records") or response.get("data") or []
    if not isinstance(records, list):
        return names
    for record in records:
        if not isinstance(record, dict):
            continue
        doc = record.get("document")
        if not doc and isinstance(record.get("segment"), dict):
            doc = record["segment"].get("document")
        if isinstance(doc, dict) and doc.get("name"):
            names.append(str(doc["name"]))
        elif record.get("document_name"):
            names.append(str(record["document_name"]))
    return list(dict.fromkeys(names))


def _run_retrieval_tests(args: argparse.Namespace, project_key: str, enabled: bool) -> list[dict[str, Any]]:
    queries = _retrieval_queries(project_key)
    if not enabled:
        return [{"query": query, "hit_documents": []} for query in queries]
    results: list[dict[str, Any]] = []
    for query in queries:
        response = _request_json(
            args,
            "POST",
            f"/datasets/{args.dataset_id}/retrieve",
            payload={
                "query": query,
                "retrieval_model": {
                    "search_method": "keyword_search",
                    "reranking_enable": False,
                    "reranking_model": None,
                    "reranking_mode": None,
                    "top_k": 3,
                    "score_threshold_enabled": False,
                },
            },
        )
        results.append({"query": query, "hit_documents": _extract_hit_names(response)})
    return results


def _load_context_pack(args: argparse.Namespace) -> str | None:
    values: list[str] = []
    if args.context_pack:
        values.append(args.context_pack)
    if args.context_pack_file:
        values.append(Path(args.context_pack_file).expanduser().read_text(encoding="utf-8"))
    return "\n\n".join(values) if values else None


def _build_result(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode not in VALID_MODES:
        raise SystemExit(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    if args.scan_depth not in VALID_SCAN_DEPTHS:
        raise SystemExit(f"scan_depth must be one of: {', '.join(sorted(VALID_SCAN_DEPTHS))}")
    if not args.dataset_id:
        raise SystemExit("dataset_id is required.")

    repo_ref = args.repo_ref or "main"
    repo_subdir = args.repo_subdir or ""
    verified_at = args.verified_at or _today()
    aliases = _parse_aliases(args.project_aliases)
    context_pack = _load_context_pack(args)
    cleanup_dir: Path | None = None

    try:
        if args.repo_url:
            input_mode = "git"
            facts, cleanup_dir = _scan_repo(
                repo_url=args.repo_url,
                repo_ref=repo_ref,
                repo_subdir=repo_subdir,
                scan_depth=args.scan_depth,
                project_key=args.project_key,
                aliases=aliases,
                verified_at=verified_at,
                context_pack=context_pack,
            )
        elif context_pack:
            input_mode = "context_pack"
            facts = _facts_from_context_pack(
                context_pack=context_pack,
                repo_path=args.repo_path,
                git_sha=args.git_sha,
                repo_url=args.repo_url,
                repo_ref=repo_ref,
                repo_subdir=repo_subdir,
                project_key=args.project_key,
                aliases=aliases,
                verified_at=verified_at,
            )
        else:
            raise SystemExit("Provide repo_url for Git mode or context_pack/context_pack_file for Context Pack mode.")

        documents = _generate_documents(facts)
        quality_check = _quality_check(facts, documents)
        write_result = _write_documents(args, facts, documents) if quality_check["passed"] else {"written": False, "document_ids": [], "error": "quality check failed"}
        retrieval_tests_enabled = bool(write_result.get("written")) and not write_result.get("error")
        retrieval_test_queries = _run_retrieval_tests(args, facts["project_key"], retrieval_tests_enabled)
        return {
            "dataset_id": args.dataset_id,
            "mode": args.mode,
            "input_mode": input_mode,
            "project_key": facts["project_key"],
            "repo_url": facts["repo_url"],
            "repo_ref": facts["repo_ref"],
            "repo_subdir": facts["repo_subdir"],
            "commit_sha": facts["commit_sha"],
            "verified_at": facts["verified_at"],
            "documents": documents,
            "quality_check": quality_check,
            "write_result": write_result,
            "retrieval_test_queries": retrieval_test_queries,
        }
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Dify project knowledge cards from a Git repo or context pack.")
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default="dry_run")
    parser.add_argument("--project-key", default=None)
    parser.add_argument("--project-aliases", default=None)
    parser.add_argument("--verified-at", default=None)
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--repo-ref", default="main")
    parser.add_argument("--repo-subdir", default="")
    parser.add_argument("--scan-depth", choices=sorted(VALID_SCAN_DEPTHS), default="standard")
    parser.add_argument("--context-pack", default=None)
    parser.add_argument("--context-pack-file", default=None)
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--git-sha", default=None)
    parser.add_argument("--base-url", default=os.environ.get("DIFY_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout", type=int, default=60)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = _build_result(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
