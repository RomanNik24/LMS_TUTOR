"""Единая проверка ``scripts/check.py``: шаг не может зависнуть навсегда (аудит 2026-10-08, п. 2).

Раньше ``check.py`` ждал шаг без ограничения времени, а на Windows зависший дочерний процесс теста
держал вывод — проверка не завершалась никогда.
"""

import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Запас на медленный ПК: шаг с таймаутом 2 с обязан закончиться заметно раньше.
GUARD_SECONDS = 30


@pytest.fixture(scope="module")
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_script", ROOT / "scripts" / "check.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_script"] = module
    spec.loader.exec_module(module)
    return module


def _run_with_guard(check: ModuleType, step: object) -> tuple[object, float, str]:
    """Запустить шаг в отдельном потоке: если он зависнет, тест упадёт, а не повиснет."""
    result: list[tuple[object, float, str]] = []
    worker = threading.Thread(target=lambda: result.append(check._run_step(step)), daemon=True)
    worker.start()
    worker.join(GUARD_SECONDS)
    assert result, f"шаг не завершился за {GUARD_SECONDS} с — check.py завис бы"
    return result[0]


def test_step_pass_and_fail(check: ModuleType) -> None:
    ok = check.Step("ok", (sys.executable, "-c", "print('hello')"))
    bad = check.Step("bad", (sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"))
    assert _run_with_guard(check, ok)[0] == check.Status.PASS
    status, _, output = _run_with_guard(check, bad)
    assert status == check.Status.FAIL
    assert "boom" in output


def test_hanging_step_is_stopped_by_timeout(check: ModuleType) -> None:
    step = check.Step("hang", (sys.executable, "-c", "import time; time.sleep(120)"), timeout=2)
    status, elapsed, output = _run_with_guard(check, step)
    assert status == check.Status.FAIL
    assert elapsed < GUARD_SECONDS
    assert "не завершился за 2 с" in output


def test_child_holding_output_does_not_hang_check(check: ModuleType) -> None:
    """Как в зависании на Windows: внук держит вывод шага, а сам шаг завис."""
    script = (
        "import subprocess, sys, time;"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
        "print('child started', flush=True); time.sleep(120)"
    )
    step = check.Step("orphan", (sys.executable, "-c", script), timeout=2)
    status, elapsed, output = _run_with_guard(check, step)
    assert status == check.Status.FAIL
    assert elapsed < GUARD_SECONDS
    assert "не завершился" in output
