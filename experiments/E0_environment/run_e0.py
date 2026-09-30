"""
run_e0.py — E0 环境与可重复性验收。

协议 §E0：固定版本、pytest 通过率、MCP 健康检查、服务启动/停止稳定性、
无状态工具连续调用成功率和平均延迟。
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

# 将 experiments/ 加入路径，使 framework 可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from framework.backend_client import BackendClient
from framework.condition import Condition
from framework.run_manager import RunContext, load_config
from framework.progress import completed, failed, progress, status

console = Console()

EXPERIMENT_ID = "E0"
N_MCP_LAUNCH_CYCLES = 10    # 协议：连续启动/停止 10 次
N_STATELESS_CALLS = 20       # 协议：连续调用 20 次无状态工具


def run_pytest(ctx: RunContext) -> dict:
    """运行 backend 单元测试，记录通过率。"""
    backend_root = Path(__file__).resolve().parents[2] / "backend"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(backend_root),
    )
    stdout = result.stdout + result.stderr
    ctx.append_stdout(stdout)

    passed = failed = errors = 0
    for line in stdout.splitlines():
        if " passed" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "passed":
                    try:
                        passed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if p == "failed":
                    try:
                        failed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if p == "error" in p:
                    try:
                        errors = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass

    total = passed + failed + errors
    pass_rate = passed / total if total > 0 else 0.0
    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": total,
        "pass_rate": round(pass_rate, 4),
        "returncode": result.returncode,
    }


def check_backend_health(client: BackendClient) -> dict:
    """检查 /health 和 /api/system/software。"""
    health_ok = client.health()
    software: dict = {}
    try:
        software = client.get_software_info()
    except Exception as exc:  # noqa: BLE001
        software = {"error": str(exc)}
    models: dict = {}
    try:
        models = client.get_model_info()
    except Exception as exc:  # noqa: BLE001
        models = {"error": str(exc)}

    return {
        "health_ok": health_ok,
        "software": software,
        "models": models,
    }


def probe_stateless_tool(client: BackendClient, n: int = N_STATELESS_CALLS) -> dict:
    """
    连续调用 /health N 次作为无状态工具代理，记录成功率和延迟。
    当 MCP 工具的无状态 ping 接口可用后，应替换为具体工具调用。
    """
    successes = 0
    latencies: list[float] = []
    errors: list[str] = []

    for i in progress(range(n), total=n, description="进度", unit="item"):
        t0 = time.perf_counter()
        ok = client.health()
        elapsed = time.perf_counter() - t0
        if ok:
            successes += 1
            latencies.append(elapsed)
        else:
            errors.append(f"call_{i}: health returned false")

    success_rate = successes / n
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    p95_latency = (
        sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0
    )

    return {
        "n_calls": n,
        "successes": successes,
        "success_rate": round(success_rate, 4),
        "avg_latency_s": round(avg_latency, 4),
        "p95_latency_s": round(p95_latency, 4),
        "errors": errors,
    }


def check_mcp_launch_stability(ctx: RunContext, n: int = N_MCP_LAUNCH_CYCLES) -> dict:
    """
    通过反复调用 /api/system/software 中的 mcp_servers 字段
    模拟 MCP 服务可用性检测（n 次）。
    实际 MCP 启动/停止循环需要 backend 提供专用接口后增强。
    """
    client = BackendClient(Condition.P)
    success_count = 0
    failures: list[str] = []

    for i in progress(range(n), total=n, description="进度", unit="item"):
        try:
            info = client.get_software_info()
            mcp_servers = info.get("mcp_servers", [])
            all_connected = all(s.get("connected", False) for s in mcp_servers)
            if all_connected:
                success_count += 1
            else:
                failures.append(f"cycle_{i}: not all MCP servers connected")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"cycle_{i}: {exc}")
            ctx.append_stderr(f"MCP cycle {i} error: {exc}")

    return {
        "n_cycles": n,
        "success_count": success_count,
        "success_rate": round(success_count / n, 4),
        "failures": failures,
        # 协议验收标准：成功率 ≥ 0.95
        "meets_threshold": success_count / n >= 0.95,
    }


def print_summary(results: dict) -> None:
    table = Table(title="E0 环境与可重复性验收结果", show_header=True)
    table.add_column("检查项", style="cyan", min_width=30)
    table.add_column("结果", style="green")
    table.add_column("达标", style="bold")

    pr = results.get("pytest", {})
    table.add_row(
        "pytest 通过率",
        f"{pr.get('passed', '?')}/{pr.get('total', '?')} ({pr.get('pass_rate', 0):.1%})",
        "✓" if pr.get("pass_rate", 0) >= 1.0 else "✗",
    )

    mcp = results.get("mcp_stability", {})
    table.add_row(
        "MCP 稳定性",
        f"{mcp.get('success_count', '?')}/{mcp.get('n_cycles', '?')} ({mcp.get('success_rate', 0):.1%})",
        "✓" if mcp.get("meets_threshold") else "✗",
    )

    probe = results.get("stateless_probe", {})
    table.add_row(
        "无状态工具调用成功率",
        f"{probe.get('success_rate', 0):.1%}  avg={probe.get('avg_latency_s', 0):.3f}s  p95={probe.get('p95_latency_s', 0):.3f}s",
        "✓" if probe.get("success_rate", 0) >= 0.95 else "✗",
    )

    health = results.get("health", {})
    table.add_row(
        "Backend /health",
        "ok" if health.get("health_ok") else "FAIL",
        "✓" if health.get("health_ok") else "✗",
    )

    console.print(table)


def main() -> None:
    cfg = load_config()
    ctx = RunContext.create(EXPERIMENT_ID, "system", "E0_check", replicate=1, base_cfg=cfg)
    console.print(f"\n[bold]E0 实验开始[/bold]  run_id={ctx.run_id}")

    results: dict = {}

    # 1. pytest
    console.print("\n[yellow]1/4 运行 pytest...[/yellow]")
    results["pytest"] = run_pytest(ctx)

    # 2. backend 健康检查
    console.print("[yellow]2/4 Backend 健康检查...[/yellow]")
    client = BackendClient(Condition.P)
    results["health"] = check_backend_health(client)

    # 3. MCP 稳定性
    console.print("[yellow]3/4 MCP 服务稳定性检测...[/yellow]")
    results["mcp_stability"] = check_mcp_launch_stability(ctx)

    # 4. 无状态工具连续调用
    console.print("[yellow]4/4 无状态工具连续调用...[/yellow]")
    results["stateless_probe"] = probe_stateless_tool(client)

    # 持久化
    ctx.write("model_outputs.json", results)
    ctx.write("input.json", {"experiment": EXPERIMENT_ID, "config": cfg})

    overall_ok = (
        results["pytest"].get("pass_rate", 0) >= 1.0
        and results["health"].get("health_ok", False)
        and results["mcp_stability"].get("meets_threshold", False)
        and results["stateless_probe"].get("success_rate", 0) >= 0.95
    )
    ctx.finalize(success=overall_ok)

    print_summary(results)
    console.print(
        f"\n[bold {'green' if overall_ok else 'red'}]"
        f"E0 验收{'通过' if overall_ok else '未通过'}[/bold {'green' if overall_ok else 'red'}]  "
        f"结果目录: {ctx.run_dir}"
    )


if __name__ == "__main__":
    main()
