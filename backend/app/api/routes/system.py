from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException

from app.core.model_config import describe_all
from app.runtime_checks import check_mcp_servers, ensure_runtime_ready

router = APIRouter(prefix="/api/system", tags=["system"])


def _existing_path(path: str) -> str | None:
    return path if path and Path(path).exists() else None


def _detect_inventor() -> dict[str, Any]:
    candidates = [
        r"C:\Program Files\Autodesk\Inventor 2026\Bin\Inventor.exe",
        r"C:\Program Files\Autodesk\Inventor 2025\Bin\Inventor.exe",
        r"C:\Program Files\Autodesk\Inventor 2024\Bin\Inventor.exe",
    ]
    found = next((_existing_path(p) for p in candidates if _existing_path(p)), None)
    return {
        "installed": found is not None,
        "path": found,
        "project_extensions": [".ipt", ".iam", ".idw", ".ipj"],
    }


def _detect_ansys() -> dict[str, Any]:
    runwb2 = os.getenv("ANSYS_RUNWB2", r"D:\Program Files\ANSYS Inc\v251\Framework\bin\Win64\RunWB2.exe")
    mapdl = os.getenv("ANSYS_MAPDL", r"D:\Program Files\ANSYS Inc\v251\ansys\bin\winx64\ANSYS251.exe")
    return {
        "runwb2": runwb2,
        "runwb2_exists": _existing_path(runwb2) is not None,
        "mapdl": mapdl,
        "mapdl_exists": _existing_path(mapdl) is not None,
    }


@router.get("/software")
def detect_software() -> dict[str, Any]:
    inventor = _detect_inventor()
    ansys = _detect_ansys()
    mcp_servers = check_mcp_servers()
    mcp_ok = all(s.get("connected") for s in mcp_servers)
    return {
        "platform": os.name,
        "inventor": inventor,
        "ansys": ansys,
        "mcp_servers": mcp_servers,
        "ready": inventor.get("installed") and mcp_ok,
    }


@router.get("/models")
def effective_models() -> dict[str, Any]:
    """各槽位生效的模型配置（密钥脱敏），用于核对实际在用的模型。"""
    return {"models": describe_all()}


@router.get("/runtime")
async def detect_runtime() -> dict[str, Any]:
    try:
        return {"status": "ok", "services": await ensure_runtime_ready()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
