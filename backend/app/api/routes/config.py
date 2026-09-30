"""模型与软件配置的读写接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import env_file
from app.core.model_config import describe_all, load_env, mask_secret

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigItem(BaseModel):
    key: str
    value: str
    section: str
    sensitive: bool
    commented: bool


class UpdateConfigRequest(BaseModel):
    values: dict[str, str]


@router.get("/env")
def get_env(reveal: bool = False) -> dict[str, Any]:
    """返回 .env 全部键值，按分节聚合。敏感项默认脱敏。"""
    grouped: dict[str, list[ConfigItem]] = {}
    for entry in env_file.read_entries():
        shown = entry.value
        if entry.sensitive and not reveal:
            shown = mask_secret(entry.value)
        grouped.setdefault(entry.section or "其他", []).append(
            ConfigItem(
                key=entry.key,
                value=shown,
                section=entry.section,
                sensitive=entry.sensitive,
                commented=entry.commented,
            )
        )
    sections = [{"section": name, "items": items} for name, items in grouped.items()]
    return {"sections": sections}


@router.put("/env")
def update_env(req: UpdateConfigRequest) -> dict[str, Any]:
    """回写 .env。脱敏占位（形如 sk-****...abcd）会被跳过，避免把掩码写回。"""
    if not req.values:
        raise HTTPException(status_code=400, detail="没有要更新的配置项")

    cleaned = {
        key: value
        for key, value in req.values.items()
        if value is not None and "***" not in value and "…" not in value
    }
    if not cleaned:
        raise HTTPException(status_code=400, detail="所有提交值都是脱敏占位，未做修改")

    added = env_file.write_values(cleaned)
    load_env(force=True)
    return {"updated": sorted(cleaned.keys()), "added": added}


@router.get("/models")
def effective_models() -> dict[str, Any]:
    """各槽位当前生效的模型配置（密钥脱敏）。"""
    load_env(force=True)
    return {"models": describe_all()}
