import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

from riffnel_memguard import benchmark  # noqa: E402


def test_cases_file_matches_generator():
    import generate
    assert json.loads((ROOT / "benchmark" / "cases.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(generate.generate(), ensure_ascii=False))


def test_benchmark_runs_and_results_file_is_current():
    res = benchmark.run(ROOT / "benchmark" / "cases.json")
    assert res["n_cases"] == 60
    assert benchmark.render(res).rstrip("\n") == (ROOT / "benchmark" / "RESULTS.md").read_text(encoding="utf-8").rstrip("\n")
