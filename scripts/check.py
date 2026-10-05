#!/usr/bin/env python3
"""Единая команда проверки проекта MY_LMS (задача T0.10).

Скрипт последовательно выполняет backend- и frontend-проверки, печатает
результат по каждому шагу в виде таблицы и завершается ненулевым кодом,
если хотя бы один шаг провалился.

Только стандартная библиотека Python, кроссплатформенно (Windows/macOS/Linux).
Комментарии и вывод — на русском согласно docs/06_agent_rules.md.

Примеры:
    uv run python scripts/check.py                # всё
    uv run python scripts/check.py --backend-only # только backend
    uv run python scripts/check.py --frontend-only

Код возврата: 0 — все проверки прошли (SKIPPED не считается ошибкой),
1 — есть провалившиеся шаги, 2 — ошибка самого запуска.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Корень репозитория — родительский каталог этого файла (repo/scripts/check.py).
REPO_ROOT = Path(__file__).resolve().parent.parent

# Каталог фронтенда появится в T0.11; пока его нет, frontend-шаги помечаются SKIPPED.
FRONTEND_DIR = REPO_ROOT / "frontend"

# Максимум строк вывода команды при сбое, чтобы лог оставался читаемым.
MAX_OUTPUT_LINES = 40


# Статусы шага. Через enum, а не строковые константы: ruff (S105) трактует
# присваиваемую строку "PASS" как возможный пароль и ругается на неё.
class Status(Enum):
    """Итог одного шага проверки."""

    PASS = "PASS"  # noqa: S105 - это статус проверки, не пароль
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


STEP_WIDTH = 20
STATUS_WIDTH = 7


@dataclass(frozen=True)
class Step:
    """Одна проверка: человекочитаемое имя и команда для запуска."""

    name: str
    command: tuple[str, ...]
    # None — запускать из корня репозитория.
    cwd: Path | None = None


# Порядок шагов важен: сначала быстрые статические проверки, затем тесты.
BACKEND_STEPS: tuple[Step, ...] = (
    Step("ruff check", ("uv", "run", "ruff", "check", ".")),
    Step("ruff format", ("uv", "run", "ruff", "format", "--check", ".")),
    Step("mypy --strict src", ("uv", "run", "mypy", "--strict", "src")),
    Step("pytest", ("uv", "run", "pytest", "-q")),
)

FRONTEND_STEPS: tuple[Step, ...] = (
    Step("pnpm lint", ("pnpm", "lint"), FRONTEND_DIR),
    Step("pnpm typecheck", ("pnpm", "typecheck"), FRONTEND_DIR),
    Step("pnpm test --run", ("pnpm", "test", "--run"), FRONTEND_DIR),
    Step("pnpm build", ("pnpm", "build"), FRONTEND_DIR),
)


def _tail(output: str) -> str:
    """Возвращает последние строки вывода команды — самое информативное при сбое."""
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return "(пустой вывод)"
    if len(lines) <= MAX_OUTPUT_LINES:
        return "\n".join(lines)
    hidden = len(lines) - MAX_OUTPUT_LINES
    return "\n".join([f"... (пропущено строк: {hidden})", *lines[-MAX_OUTPUT_LINES:]])


def _run_step(step: Step) -> tuple[Status, float, str]:
    """Выполняет шаг и возвращает (статус, длительность в секундах, вывод при сбое).

    Статус SKIPPED возвращается, если в рабочем каталоге шага нет.
    """
    work_dir = step.cwd if step.cwd is not None else REPO_ROOT
    if step.cwd is not None and not work_dir.is_dir():
        return Status.SKIPPED, 0.0, f"каталог {work_dir.relative_to(REPO_ROOT)} ещё не создан"

    executable = step.command[0]
    if shutil.which(executable) is None:
        return Status.FAIL, 0.0, f"не найден исполняемый файл {executable} в PATH"

    started = time.monotonic()
    try:
        # S603: команды заданы самим скриптом (список аргументов), а не вводом
        # пользователя, shell=False — инъекции через оболочку невозможны.
        completed = subprocess.run(  # noqa: S603
            step.command,
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
        )
    except OSError as error:  # pragma: no cover - зависит от окружения
        return Status.FAIL, time.monotonic() - started, f"не удалось запустить: {error}"

    elapsed = time.monotonic() - started
    if completed.returncode != 0:
        return Status.FAIL, elapsed, _tail((completed.stdout or "") + (completed.stderr or ""))
    return Status.PASS, elapsed, ""


def _print_header(title: str) -> None:
    print()
    print(f"=== {title} ===")
    print(f"{'ШАГ':<{STEP_WIDTH}}  {'СТАТУС':<{STATUS_WIDTH}}  ВРЕМЯ")


def _print_row(name: str, status: Status, elapsed: float) -> None:
    # Шаги с пустым результатом (SKIPPED) показываем без времени.
    duration = "-" if status == Status.SKIPPED else f"{elapsed:.2f}s"
    print(f"{name:<{STEP_WIDTH}}  {status.value:<{STATUS_WIDTH}}  {duration}")


def _print_failure(name: str, output: str) -> None:
    """Печатает вывод упавшего шага с отступом — чтобы было видно причину."""
    print()
    print(f"--- вывод шага «{name}» ---")
    for line in output.splitlines():
        print(f"    {line}")
    print("--- конец вывода ---")


def _run_group(title: str, steps: tuple[Step, ...]) -> tuple[int, int]:
    """Выполняет группу шагов, печатает таблицу. Возвращает (успехов, падений)."""
    _print_header(title)
    passed = 0
    failed = 0
    for step in steps:
        status, elapsed, output = _run_step(step)
        _print_row(step.name, status, elapsed)
        if status == Status.PASS:
            passed += 1
        elif status == Status.FAIL:
            failed += 1
            _print_failure(step.name, output)
    return passed, failed


def main(argv: list[str] | None = None) -> int:
    """Точка входа: разбирает аргументы, прогоняет группы, печатает итог."""
    parser = argparse.ArgumentParser(
        description="Единая проверка проекта MY_LMS: backend + frontend.",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="проверить только backend (ruff, ruff format, mypy, pytest)",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="проверить только frontend (pnpm lint, typecheck, test, build)",
    )
    args = parser.parse_args(argv)

    # Одновременно оба флага бессмысленны: не молча делаем выбор, а сообщаем.
    if args.backend_only and args.frontend_only:
        print("Нельзя одновременно указать --backend-only и --frontend-only.", file=sys.stderr)
        return 2

    print("Проверка проекта MY_LMS")
    print(f"Каталог: {REPO_ROOT}")
    print(f"Python: {sys.version.split()[0]}")

    total_passed = 0
    total_failed = 0

    if not args.frontend_only:
        passed, failed = _run_group("backend", BACKEND_STEPS)
        total_passed += passed
        total_failed += failed

    if not args.backend_only:
        passed, failed = _run_group("frontend", FRONTEND_STEPS)
        total_passed += passed
        total_failed += failed

    print()
    if total_failed:
        print(f"ИТОГ: пройдено {total_passed}, провалено {total_failed} — ALL CHECKS FAILED")
        return 1

    print(f"ИТОГ: пройдено {total_passed}, провалено 0 — ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
