import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    ROOT / "tests" / "test_effect_framework_big.py",
    ROOT / "tests" / "test_real_cards_batch.py",
    ROOT / "tests" / "test_tier36_complete.py",
]

env = os.environ.copy()
env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

for test in TESTS:
    print(f"\n=== {test.name} ===", flush=True)
    subprocess.run([sys.executable, str(test)], cwd=ROOT, env=env, check=True)

print("\nALL CARD/ENGINE TEST SUITES PASSED")
