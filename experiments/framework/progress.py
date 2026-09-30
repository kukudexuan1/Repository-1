"""统一的实验进度与状态输出工具。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

from rich.console import Console
from tqdm import tqdm

T = TypeVar("T")
console = Console()


def announce(experiment_id: str, message: str) -> None:
    console.print(f"[bold cyan][{experiment_id}][/bold cyan] {message}")


def status(experiment_id: str, message: str, *, success: bool | None = None) -> None:
    if success is None:
        style = "yellow"
        marker = "..."
    elif success:
        style = "green"
        marker = "OK"
    else:
        style = "red"
        marker = "FAIL"
    console.print(f"[{style}][{experiment_id}] {marker} {message}[/{style}]")


def progress(
    items: Iterable[T],
    *,
    total: int | None = None,
    description: str,
    unit: str = "item",
) -> Iterator[T]:
    return iter(tqdm(items, total=total, desc=description, unit=unit, dynamic_ncols=True))


def completed(experiment_id: str, message: str) -> None:
    status(experiment_id, message, success=True)


def failed(experiment_id: str, message: str) -> None:
    status(experiment_id, message, success=False)
