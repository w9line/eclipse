from __future__ import annotations

import base64
import json
import math
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple
from metadata_analyzer import scan_file_for_metadata


_PATTERN_DEFS: Sequence[tuple[str, str]] = [
    ("aws_access_key_id", r"AKIA[0-9A-Z]{16}"),
    ("aws_secret_access_key", r"(?<![A-Za-z0-9/+])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
    ("gcp_service_account_key", r'"type":\s*"service_account"'),
    ("gcp_api_key", r"AIza[0-9A-Za-z\-_]{35}"),
    ("azure_storage_key", r"(?i)AccountKey\s*=\s*[A-Za-z0-9+/=]{40,}"),
    ("github_token", r"ghp_[A-Za-z0-9]{36}"),
    ("github_fine_grained", r"github_pat_[A-Za-z0-9_]{82,110}"),
    ("gitlab_personal_token", r"glpat-[A-Za-z0-9-_]{20,40}"),
    ("bitbucket_app_password", r"x-token-auth:[A-Za-z0-9]{20,40}"),
    ("stripe_secret_key", r"sk_live_[0-9a-zA-Z]{24,99}"),
    ("stripe_restricted_key", r"rk_live_[0-9a-zA-Z]{24,99}"),
    ("paypal_bearer_token", r"access_token\$production\$[A-Za-z0-9._-]{10,}"),
    ("google_oauth_client_id", r"[0-9]{10,}-[0-9a-z]{32}\.apps\.googleusercontent\.com"),
    ("google_oauth_client_secret", r"(?i)google.*client.*secret['\"]?\s*[:=]\s*['\"][0-9A-Za-z-_]{8,}"),
    ("firebase_api_key", r"AIza[0-9A-Za-z\-_]{35}"),
    ("telegram_bot_token", r"\b\d{8,12}:[A-Za-z0-9_-]{30,60}\b"),
    ("discord_bot_token", r"[\w-]{24}\.[\w-]{6}\.[\w-]{27}"),
    ("slack_token", r"xox[baprs]-[A-Za-z0-9]{10,48}"),
    ("twilio_api_key", r"SK[0-9a-fA-F]{32}"),
    ("pg_connection_uri", r"postgres(?:ql)?://[^\s]+"),
    ("mysql_connection_uri", r"mysql://[^\s]+"),
    ("mongodb_connection_uri", r"mongodb(?:\+srv)?://[^\s]+"),
    ("redis_connection_uri", r"redis://[^\s]+"),
    ("generic_password", r"(?i)password\s*[:=]\s*[\"']?[^\"'\s]{6,}"),
    ("generic_secret", r"(?i)secret\s*[:=]\s*[\"']?[A-Za-z0-9/+_.-]{8,}"),
    ("jwt_token", r"eyJ[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]{10,}"),
    ("private_key_header", r"-----BEGIN (RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone", r"\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]\d{3,4}[\s-]?\d{3,4}"),
]

_COMPILED_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern)) for name, pattern in _PATTERN_DEFS
]




@dataclass
class ScanConfig:
    repo_path: Path
    max_file_size: int = 1_000_000  
    scan_history: bool = False
    history_commit_limit: Optional[int] = None
    entropy_threshold: float = 4.2
    include_entropy: bool = True
    include_patterns: bool = True
    rules_config_path: Optional[Path] = None




@dataclass
class Finding:
    source: str
    path: str
    kind: str
    excerpt: str
    start: int
    end: int
    entropy: Optional[float] = None
    category: str = "secret"
    severity: str = "medium"
    hint: Optional[str] = None


@dataclass
class ScanResult:
    repo_path: str
    findings: List[Finding]

    def to_json(self) -> str:
        return json.dumps(
            {
                "repo_path": self.repo_path,
                "findings": [asdict(f) for f in self.findings],
            },
            ensure_ascii=False,
            indent=2,
        )


def _run_git(args: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode(errors="ignore")


def _should_skip_path(path: Path) -> bool:
    if ".git" in path.parts:
        return True
    if "__pycache__" in path.parts:
        return True
    suffix = path.suffix.lower()
    meta_ok = {".docx", ".xlsx", ".pptx", ".pdf", ".jpg", ".jpeg", ".png"}
    binary_suffixes = {
        ".pyc", ".so", ".dll", ".exe", ".zip", ".tar", ".gz", ".7z",
        ".mp3", ".mp4", ".avi", ".mov", ".ogg", ".ico", ".woff", ".woff2"
    }
    return suffix in binary_suffixes and suffix not in meta_ok


def _iter_workdir_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if _should_skip_path(path):
            continue
        yield path


def _is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    entropy = -sum((count / length) * math.log2(count / length) for count in counts.values())
    return entropy


def _load_patterns_from_config(path: Path) -> Sequence[tuple[str, re.Pattern[str]]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise FileNotFoundError(f"Rules config not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in rules config {path}: {e}") from e

    rules = raw.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Rules config must contain 'rules' list.")

    compiled: List[tuple[str, re.Pattern[str]]] = []
    for item in rules:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        pattern = item.get("pattern")
        if not name or not pattern:
            continue
        compiled.append((str(name), re.compile(str(pattern))))
    return compiled or _COMPILED_PATTERNS


def _scan_content(
    text: str,
    source: str,
    path: str,
    include_patterns: bool,
    include_entropy: bool,
    entropy_threshold: float,
) -> Iterator[Finding]:
    if include_patterns:
        for name, pattern in _COMPILED_PATTERNS:
            for match in pattern.finditer(text):
                excerpt = text[max(0, match.start() - 20) : match.end() + 20]
                yield Finding(
                    source=source,
                    path=path,
                    kind=name,
                    excerpt=excerpt[:200],
                    start=match.start(),
                    end=match.end(),
                    entropy=None,
                )

    if include_entropy:
        for match in re.finditer(r"[A-Za-z0-9+/=]{20,}", text):
            token = match.group(0).encode()
            entropy = _shannon_entropy(token)
            if entropy >= entropy_threshold:
                excerpt = text[max(0, match.start() - 10) : match.end() + 10]
                yield Finding(
                    source=source,
                    path=path,
                    kind="high_entropy",
                    excerpt=excerpt[:200],
                    start=match.start(),
                    end=match.end(),
                    entropy=entropy,
                )


def _read_file_safe(path: Path, max_size: int) -> Optional[str]:
    try:
        if path.stat().st_size > max_size:
            return None
        data = path.read_bytes()
        if _is_probably_binary(data):
            return None
        return data.decode(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


def scan_workdir(cfg: ScanConfig) -> List[Finding]:
    file_paths = list(_iter_workdir_files(cfg.repo_path))
    max_workers = min(32, (os.cpu_count() or 1) + 4)

    def scan_single_file(file_path: Path) -> List[Finding]:
        local_findings = []

        content = _read_file_safe(file_path, cfg.max_file_size)
        if content is not None:
            local_findings.extend(
                _scan_content(
                    content,
                    source="workdir",
                    path=str(file_path.relative_to(cfg.repo_path)),
                    include_patterns=cfg.include_patterns,
                    include_entropy=cfg.include_entropy,
                    entropy_threshold=cfg.entropy_threshold,
                )
            )

        meta_findings = scan_file_for_metadata(
            file_path,
            source="workdir",
            max_size=cfg.max_file_size
        )
        for f in meta_findings:
            f.path = str(file_path.relative_to(cfg.repo_path))
        local_findings.extend(meta_findings)

        return local_findings

    all_findings: List[Finding] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(scan_single_file, fp): fp for fp in file_paths
        }
        for future in as_completed(future_to_path):
            try:
                findings = future.result()
                all_findings.extend(findings)
            except Exception as e:
                fp = future_to_path[future]
                print(f"⚠️ Error scanning {fp}: {e}", file=sys.stderr)

    return all_findings



def _iter_commits(cfg: ScanConfig) -> Iterable[str]:
    args = ["rev-list", "--all", "--remotes", "--tags"]
    if cfg.history_commit_limit:
        args.append(f"--max-count={cfg.history_commit_limit}")
    output = _run_git(args, cfg.repo_path)
    for line in output.splitlines():
        if line.strip():
            yield line.strip()


def _iter_commit_files(commit: str, repo_path: Path) -> Iterable[str]:
    output = _run_git(["ls-tree", "-r", "--name-only", commit], repo_path)
    for line in output.splitlines():
        rel = line.strip()
        if not rel:
            continue
        if _should_skip_path(Path(rel)):
            continue
        yield rel


def _read_blob(commit: str, file_path: str, repo_path: Path, max_size: int) -> Optional[str]:
    try:
        size_output = _run_git(["cat-file", "-s", f"{commit}:{file_path}"], repo_path)
        size = int(size_output.strip())
        if size > max_size:
            return None
        blob = _run_git(["show", f"{commit}:{file_path}"], repo_path)
        return blob
    except subprocess.CalledProcessError:
        return None


def scan_history(cfg: ScanConfig) -> List[Finding]:
    commit_files: List[Tuple[str, str]] = []
    for commit in _iter_commits(cfg):
        for file_path in _iter_commit_files(commit, cfg.repo_path):
            commit_files.append((commit, file_path))

    max_workers = min(16, (os.cpu_count() or 1) + 4)

    def scan_commit_file(pair: Tuple[str, str]) -> List[Finding]:
        commit, file_path = pair
        content = _read_blob(commit, file_path, cfg.repo_path, cfg.max_file_size)
        if content is None:
            return []
        return list(
            _scan_content(
                content,
                source=commit,
                path=file_path,
                include_patterns=cfg.include_patterns,
                include_entropy=cfg.include_entropy,
                entropy_threshold=cfg.entropy_threshold,
            )
        )

    all_findings: List[Finding] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(scan_commit_file, pair) for pair in commit_files]
        for future in as_completed(futures):
            try:
                all_findings.extend(future.result())
            except Exception as e:
                print(f"⚠️ Error in history scan: {e}", file=sys.stderr)

    return all_findings



_KIND_CATEGORY = {
    "aws_access_key_id": "secret",
    "aws_secret_access_key": "secret",
    "gcp_service_account_key": "secret",
    "gcp_api_key": "secret",
    "azure_storage_key": "secret",
    "github_token": "secret",
    "github_fine_grained": "secret",
    "gitlab_personal_token": "secret",
    "bitbucket_app_password": "secret",
    "stripe_secret_key": "secret",
    "stripe_restricted_key": "secret",
    "paypal_bearer_token": "secret",
    "google_oauth_client_id": "secret",
    "google_oauth_client_secret": "secret",
    "firebase_api_key": "secret",
    "telegram_bot_token": "secret",
    "discord_bot_token": "secret",
    "slack_token": "secret",
    "twilio_api_key": "secret",
    "pg_connection_uri": "infra",
    "mysql_connection_uri": "infra",
    "mongodb_connection_uri": "infra",
    "redis_connection_uri": "infra",
    "generic_password": "secret",
    "generic_secret": "secret",
    "jwt_token": "secret",
    "private_key_header": "secret",
    "email": "pii",
    "phone": "pii",
    "high_entropy": "secret",
}

_KIND_BASE_SEVERITY = {
    "aws_secret_access_key": "critical",
    "private_key_header": "critical",
    "stripe_secret_key": "critical",
    "stripe_restricted_key": "critical",
    "paypal_bearer_token": "critical",
    "github_token": "high",
    "github_fine_grained": "high",
    "gitlab_personal_token": "high",
    "bitbucket_app_password": "high",
    "telegram_bot_token": "high",
    "discord_bot_token": "high",
    "slack_token": "high",
    "twilio_api_key": "high",
    "gcp_service_account_key": "high",
    "gcp_api_key": "high",
    "firebase_api_key": "high",
    "azure_storage_key": "high",
    "pg_connection_uri": "high",
    "mysql_connection_uri": "high",
    "mongodb_connection_uri": "high",
    "redis_connection_uri": "high",
    "generic_password": "medium",
    "generic_secret": "medium",
    "jwt_token": "medium",
    "aws_access_key_id": "medium",
    "google_oauth_client_id": "low",
    "google_oauth_client_secret": "medium",
    "email": "low",
    "phone": "low",
    "high_entropy": "medium",
}

def _severity_rank(level: str) -> int:
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return order.get(level, 2)

def _max_severity(a: str, b: str) -> str:
    return a if _severity_rank(a) >= _severity_rank(b) else b

def _enrich_finding(f: Finding) -> None:
    kind = f.kind
    path = f.path.lower()

    f.category = _KIND_CATEGORY.get(kind, "secret")
    base_sev = _KIND_BASE_SEVERITY.get(kind, "medium")
    severity = base_sev

    filename = os.path.basename(path)
    if filename.startswith(".env") or filename in {"env", "secrets"}:
        severity = _max_severity(severity, "high")
    if "config" in filename or "/config/" in path:
        severity = _max_severity(severity, "high")
    if any(part in path for part in ("/prod", "/production", "k8s", "kubernetes", "docker-compose")):
        severity = _max_severity(severity, "high")

    f.severity = severity

    if f.category == "secret":
        f.hint = "Перенесите секрет в безопасное хранилище (например, переменные окружения / секреты CI) и перевыпустите ключ."
    elif f.category == "infra":
        f.hint = "Проверьте, что эти параметры инфраструктуры не раскрывают внутренние адреса/доступы извне."
    elif f.category == "pii":
        f.hint = "Убедитесь, что вы не публикуете персональные данные без необходимости."
    elif f.category == "config":
        f.hint = "Проверьте конфигурацию на корректность и безопасность."
    else:
        f.hint = None


def scan_repository(cfg: ScanConfig) -> ScanResult:
    if not cfg.repo_path.exists():
        raise FileNotFoundError(f"Repo path does not exist: {cfg.repo_path}")

    global _COMPILED_PATTERNS
    if cfg.rules_config_path is not None:
        _COMPILED_PATTERNS = _load_patterns_from_config(cfg.rules_config_path)
    else:
        default_rules_path = cfg.repo_path / "rules.json"
        if default_rules_path.exists():
            _COMPILED_PATTERNS = _load_patterns_from_config(default_rules_path)
        else:
            _COMPILED_PATTERNS = [
                (name, re.compile(pattern)) for name, pattern in _PATTERN_DEFS
            ]

    findings = scan_workdir(cfg)

    if cfg.scan_history:
        findings.extend(scan_history(cfg))

    
    uniq = {}
    for f in findings:
        key = (f.source, f.path, f.kind, f.excerpt)
        if key not in uniq:
            uniq[key] = f
    enriched = list(uniq.values())
    for f in enriched:
        _enrich_finding(f)

    return ScanResult(repo_path=str(cfg.repo_path), findings=enriched)


import sys

def main() -> None:
    repo_path = Path(os.getcwd())
    cfg = ScanConfig(repo_path=repo_path)
    result = scan_repository(cfg)
    print(result.to_json())


if __name__ == "__main__":
    main()
