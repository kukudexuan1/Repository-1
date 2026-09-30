"""
run_manager.py — RunContext：run_id 生成、目录创建、实验元数据持久化。

每次实验调用 RunContext.create() 产生一个唯一运行目录，并自动写入
run_metadata.json。运行结束后调用 .finalize() 补全 ended_at 和状态。
失败运行保留 stderr.log，不删除目录。
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_base_cfg() -> dict:
    """懒加载 config/base.yaml，避免启动时强依赖 pyyaml。"""
    import yaml  # noqa: PLC0415

    cfg_path = Path(__file__).resolve().parents[1] / "config" / "base.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_str(val: Any) -> str:
    """解析 ${VAR:-default} 格式的环境变量占位符。"""
    if not isinstance(val, str):
        return str(val)
    if val.startswith("${") and val.endswith("}"):
        inner = val[2:-1]
        if ":-" in inner:
            var, default = inner.split(":-", 1)
        else:
            var, default = inner, ""
        return os.environ.get(var, default)
    return val


def load_config() -> dict:
    """返回解析了环境变量占位符的 base.yaml 配置。"""
    raw = _load_base_cfg()

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(i) for i in node]
        return _resolve_str(node)

    return _walk(raw)


# 协议 §8 要求保存的所有文件
_REQUIRED_FILES = [
    "run_metadata.json",
    "input.json",
    "model_outputs.json",
    "tool_trace.json",
    "state_before.json",
    "state_after.json",
    "calculation_records.json",
    "ledger_snapshot.json",
    "report_files.json",
    "stdout.log",
    "stderr.log",
    "human_annotation.json",
]


class RunContext:
    """
    单次实验运行的上下文。

    run_id 格式：{experiment_id}_{case_id}_{condition}_{replicate:02d}_{timestamp}
    例：E4_G_003_P_07_20260815T055121

    使用方式：
        ctx = RunContext.create("E4", "G_003", "P", replicate=7, base_cfg=cfg)
        ctx.write("input.json", task_data)
        ctx.write("tool_trace.json", trace)
        ctx.finalize(success=True)
    """

    def __init__(self, run_dir: Path, metadata: dict) -> None:
        self.run_dir = run_dir
        self.metadata = metadata
        self.run_id: str = metadata["run_id"]
        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []

    @classmethod
    def create(
        cls,
        experiment_id: str,
        case_id: str,
        condition: str,
        replicate: int,
        base_cfg: dict | None = None,
        extra_metadata: dict | None = None,
    ) -> "RunContext":
        cfg = base_cfg or load_config()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run_id = f"{experiment_id}_{case_id}_{condition}_{replicate:02d}_{timestamp}"

        results_root = Path(__file__).resolve().parents[1] / _resolve_str(
            cfg.get("experiment", {}).get("results_dir", "results")
        )
        run_dir = results_root / experiment_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        metadata: dict[str, Any] = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "case_id": case_id,
            "condition": condition,
            "replicate": replicate,
            "model_slots": cfg.get("model_slots", ),
            "temperature": float(cfg.get("experiment", {}).get("temperature", 0.0)),
            "knowledge_version": "1.0.0",
            "backend_version": "1.0.0",
            "cad_server_version": "1.0.0",
            "cae_server_version": "1.0.0",
            "human_intervened": False,
            "started_at": _now_iso(),
            "ended_at": None,
            "status": "running",
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        ctx = cls(run_dir, metadata)
        ctx._flush_metadata()

        # 创建空文件占位，保证协议要求的目录结构完整
        for fname in _REQUIRED_FILES:
            fpath = run_dir / fname
            if not fpath.exists():
                fpath.touch()

        return ctx

    # ------------------------------------------------------------------
    # 写入辅助
    # ------------------------------------------------------------------

    def write(self, filename: str, data: Any) -> Path:
        """将 data 序列化为 JSON 写入 run_dir/filename，返回路径。"""
        fpath = self.run_dir / filename
        with fpath.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return fpath

    def append_stdout(self, line: str) -> None:
        self._stdout_lines.append(line)

    def append_stderr(self, line: str) -> None:
        self._stderr_lines.append(line)

    def log_exception(self) -> None:
        """将当前异常的 traceback 追加到 stderr 缓冲。"""
        self._stderr_lines.append(traceback.format_exc())

    def flush_logs(self) -> None:
        if self._stdout_lines:
            with (self.run_dir / "stdout.log").open("a", encoding="utf-8") as f:
                f.write("\n".join(self._stdout_lines) + "\n")
            self._stdout_lines.clear()
        if self._stderr_lines:
            with (self.run_dir / "stderr.log").open("a", encoding="utf-8") as f:
                f.write("\n".join(self._stderr_lines) + "\n")
            self._stderr_lines.clear()

    # ------------------------------------------------------------------
    # 结束
    # ------------------------------------------------------------------

    def finalize(self, success: bool, human_intervened: bool = False) -> None:
        """补全 ended_at / status，刷新日志。"""
        self.metadata["ended_at"] = _now_iso()
        self.metadata["status"] = "success" if success else "failure"
        self.metadata["human_intervened"] = human_intervened
        self._flush_metadata()
        self.flush_logs()

    def mark_tool_failure(self, tool_name: str, error: str) -> None:
        """记录工具失败（协议：工具异常记为工具失败，不删除样本）。"""
        failures_path = self.run_dir / "tool_failures.json"
        failures: list[dict] = []
        if failures_path.exists() and failures_path.stat().st_size > 0:
            with failures_path.open(encoding="utf-8") as f:
                try:
                    failures = json.load(f)
                except json.JSONDecodeError:
                    failures = []
        failures.append({"tool": tool_name, "error": error, "at": _now_iso()})
        with failures_path.open("w", encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=2)

    def _flush_metadata(self) -> None:
        with (self.run_dir / "run_metadata.json").open("w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
