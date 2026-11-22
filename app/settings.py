"""Frontend configuration; diagnostics never expose secret values."""
import os
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from config import read_env, unquote

ROOT = Path(__file__).resolve().parents[1]


def configuration_signature(settings):
    """Opaque session marker; never store or render credentials in session state."""
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode("utf-8")).hexdigest()


def read_settings():
    values = read_env()
    values.update({k: unquote(v) for k, v in os.environ.items() if k in {
        "LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY", "PART1_HANDOFF_PATH",
        "POLICY_RAG_HOME", "PROGRAMME_MAP_PATH", "SEMESTER_START"} and v})
    handoff = values.get("PART1_HANDOFF_PATH") or values.get("POLICY_RAG_HOME")
    values["PART1_HANDOFF_PATH"] = str((ROOT / handoff).resolve() if handoff else ROOT.parent / "part1_handoff")
    values["PROGRAMME_MAP_PATH"] = str((ROOT / (values.get("PROGRAMME_MAP_PATH") or "programmes.json")).resolve())
    return values


def configuration_issues(settings=None):
    settings = settings if settings is not None else read_settings()
    issues = [f"尚未配置 {k}" for k in ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY") if not settings.get(k)]
    if settings.get("LLM_ENDPOINT"):
        endpoint = urlsplit(settings["LLM_ENDPOINT"])
        if endpoint.path.rstrip("/") in {"", "/v1"}:
            issues.append("LLM_ENDPOINT 需填完整聊天接口地址，例如 https://api.deepseek.com/chat/completions，不能只填根地址。")
    root = Path(settings["PART1_HANDOFF_PATH"])
    for relative in ("policy_rag/retrieve.py", "data/policy_index.sqlite", "files"):
        if not (root / relative).exists():
            issues.append(f"Part 1 路径缺少 {relative}：{root}")
    return issues
