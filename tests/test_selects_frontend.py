import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='Node.js is required for dropdown behavior checks')
def test_settings_dropdown_position_and_keyboard_behavior():
    completed = subprocess.run(
        [NODE, 'tests/selects_frontend.cjs'], cwd=ROOT,
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'checks passed' in completed.stdout
