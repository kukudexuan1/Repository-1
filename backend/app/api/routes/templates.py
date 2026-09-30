"""设计/建模模板的读写接口（不含提示词）。

模板即 services/knowledge/data 下的 YAML：材料库、标准尺寸系列与标准件、
设计公式卡、设计任务书模板。这些是设计计算与建模的知识来源，允许前端编辑；
提示词（app/agent/prompt.py）不在此列，不通过本接口暴露。

编辑以「整文件文本」粒度进行，保存前做 YAML 语法校验，写入成功后清空知识库
缓存使改动立即生效。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.knowledge import loader

router = APIRouter(prefix="/api/templates", tags=["templates"])

DATA_DIR = loader.DATA_DIR

# 分类目录 -> 展示名。仅这些目录对前端开放。
_CATEGORIES: dict[str, str] = {
    "spec_templates": "设计任务书模板",
    "formulas": "设计公式卡",
    "materials": "材料库",
    "standards": "标准尺寸与标准件",
}


class TemplateContent(BaseModel):
    content: str


def _resolve(category: str, name: str) -> Path:
    if category not in _CATEGORIES:
        raise HTTPException(status_code=404, detail=f"未知模板分类: {category}")
    # 防目录穿越：文件名不得含分隔符
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="非法文件名")
    if not name.endswith((".yaml", ".yml")):
        raise HTTPException(status_code=400, detail="仅支持 .yaml 模板")
    path = (DATA_DIR / category / name).resolve()
    if DATA_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="路径越界")
    return path


@router.get("")
def list_templates() -> dict[str, Any]:
    """列出全部可编辑模板，按分类聚合。"""
    out = []
    for category, label in _CATEGORIES.items():
        directory = DATA_DIR / category
        files = []
        if directory.exists():
            for path in sorted(directory.glob("*.y*ml")):
                files.append({"name": path.name, "size": path.stat().st_size})
        out.append({"category": category, "label": label, "files": files})
    return {"categories": out}


@router.get("/{category}/{name}")
def read_template(category: str, name: str) -> dict[str, Any]:
    path = _resolve(category, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="模板不存在")
    return {
        "category": category,
        "name": name,
        "content": path.read_text(encoding="utf-8"),
    }


@router.put("/{category}/{name}")
def write_template(category: str, name: str, req: TemplateContent) -> dict[str, Any]:
    path = _resolve(category, name)
    import yaml

    try:
        yaml.safe_load(req.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 语法错误: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(req.content, encoding="utf-8")
    counts = loader.reload_all()
    return {"saved": name, "reload": counts}
