"""backend/.env 的结构化读写。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

_SECTION_RE = re.compile(r"^#\s*=+\s*(.*?)\s*=+\s*$")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")

# 视为敏感、前端以密码框呈现的键名片段
_SENSITIVE = ("API_KEY", "SECRET", "TOKEN", "PASSWORD")


def is_sensitive(key: str) -> bool:
    upper = key.upper()
    return any(frag in upper for frag in _SENSITIVE)


@dataclass
class EnvEntry:
    key: str
    value: str
    section: str
    sensitive: bool
    commented: bool  # 该键在 .env 中处于「被注释掉」的状态


def _read_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def read_entries() -> list[EnvEntry]:
    """把 .env 解析成有序的键值条目，附带其所属分节。"""
    entries: list[EnvEntry] = []
    section = ""
    for line in _read_lines():
        sec = _SECTION_RE.match(line)
        if sec:
            section = sec.group(1).strip()
            continue
        stripped = line.strip()
        commented = False
        candidate = line
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            commented = True
        match = _ASSIGN_RE.match(candidate)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip()
        entries.append(
            EnvEntry(
                key=key,
                value=value,
                section=section,
                sensitive=is_sensitive(key),
                commented=commented,
            )
        )
    return entries


def write_values(updates: dict[str, str]) -> list[str]:
    """把 updates 写回 .env，保留注释与分节；返回新增（原本不存在的）键列表。

    仅更新未被注释的赋值行；被注释掉的键视为「关闭」，若 updates 提供了它，
    则取消注释并赋值。原文件不存在的键追加到末尾。
    """
    lines = _read_lines()
    remaining = dict(updates)
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        target = line
        prefix_commented = stripped.startswith("#") and not _SECTION_RE.match(line)
        candidate = stripped.lstrip("#").strip() if prefix_commented else line
        match = _ASSIGN_RE.match(candidate)
        if match and match.group(1) in remaining:
            key = match.group(1)
            out.append(f"{key}={remaining.pop(key)}")
            continue
        out.append(target)

    added = list(remaining.keys())
    if remaining:
        out.append("")
        out.append("# ===== 前端新增配置 =====")
        for key, value in remaining.items():
            out.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    return added
