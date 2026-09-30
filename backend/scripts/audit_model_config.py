"""模型配置审查：核对各槽位生效的配置，以及服务端实际用哪个模型响应。

判断「实际是哪个模型」只看 HTTP 响应体的 model 字段，不看模型自述身份。
模型自述不可信：训练数据里混入其他模型的输出，就会让它自称 Claude 或 GPT，
这与实际被调用的模型无关。

用法：
    python scripts/audit_model_config.py             # 只看生效配置，不发请求
    python scripts/audit_model_config.py --probe     # 实际调用各端点核对回执
    python scripts/audit_model_config.py --no-dotenv # 复现不加载 .env 时的环境
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.qwen_client import resolve_chat_completions_endpoint  # noqa: E402
from app.core.model_config import (  # noqa: E402
    _SLOT_SPECS,
    ModelConfigError,
    ModelSlot,
    load_env,
    mask_secret,
)


def resolve_endpoint(base_url: str) -> str:
    return resolve_chat_completions_endpoint(base_url)


def report_config() -> list[ModelSlot]:
    print("=" * 78)
    print("一、各槽位生效的配置")
    print("=" * 78)

    slots: list[ModelSlot] = []
    for spec in _SLOT_SPECS.values():
        print(f"[{spec.label}]  使用方: {spec.used_by}")
        try:
            from app.core.model_config import get_slot

            slot = get_slot(spec.name)
        except ModelConfigError as exc:
            print(f"  ⛔ {exc}\n")
            continue

        print(f"  模型      : {slot.model}   （来自 {spec.model_var}）")
        print(f"  endpoint  : {slot.base_url}")
        print(f"  api_key   : {mask_secret(slot.api_key)}")

        # .env 与进程环境变量都存在同名变量时，提示哪一边生效了
        if os.getenv(spec.model_var) and spec.model_var not in _dotenv_keys():
            print(f"  注意：{spec.model_var} 来自进程环境变量，不在 .env 中")
        print()
        slots.append(slot)
    return slots


def _dotenv_keys() -> set[str]:
    try:
        from dotenv import dotenv_values

        return set(dotenv_values(ROOT / ".env").keys())
    except ImportError:
        return set()


async def probe(slot: ModelSlot, ask_identity: bool = False) -> None:
    print(f"[{slot.label}] 请求 model='{slot.model}'")

    messages = [{"role": "user", "content": "ping"}]
    # 思考型模型的推理内容也计入 max_tokens，问身份时须留足额度否则正文为空
    max_tokens = 8
    if ask_identity:
        messages = [
            {"role": "user", "content": "你是哪个模型？只回答模型名称与开发方，不要解释。"}
        ]
        max_tokens = 1024

    payload = {"model": slot.model, "messages": messages, "stream": False, "max_tokens": max_tokens}
    if slot.name == "main":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "high"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                resolve_endpoint(slot.base_url),
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {slot.api_key}",
                },
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  ⛔ 请求失败: {type(exc).__name__}: {exc}\n")
        return

    if response.status_code != 200:
        body = response.text[:400]
        print(f"  ⛔ HTTP {response.status_code}: {body}")
        print(f"  → 若提示模型无效，说明该服务并不提供 '{slot.model}'，请核对 .env 中的模型 ID\n")
        return

    data = response.json()
    served = data.get("model", "(响应中无 model 字段)")
    print("  ✓ HTTP 200")
    flag = "" if served == slot.model else "   <-- 与请求值不一致！"
    print(f"  服务端实际响应的 model = '{served}'{flag}")

    if ask_identity:
        content = ""
        try:
            content = (data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError):
            pass
        print(f"  模型自述身份 = 「{content[:200]}」")
        print("  注：自述身份仅供参考，以上面的 model 字段为准")
    print()


async def main() -> int:
    parser = argparse.ArgumentParser(description="模型配置审查")
    parser.add_argument("--probe", action="store_true", help="实际调用各端点核对（消耗少量 token）")
    parser.add_argument("--no-dotenv", action="store_true", help="不加载 .env，复现纯环境变量下的配置")
    args = parser.parse_args()

    if args.no_dotenv:
        print("已跳过 .env 加载\n")
    else:
        load_env()

    slots = report_config()

    if not args.probe:
        print("加 --probe 可实际调用端点，核对服务端回执中的 model 字段。")
        return 0

    print("=" * 78)
    print("二、服务端实际响应的模型（读响应体 model 字段）")
    print("=" * 78)
    for idx, slot in enumerate(slots):
        await probe(slot, ask_identity=(idx == 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
