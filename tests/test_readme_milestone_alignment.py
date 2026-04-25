from pathlib import Path


def test_readme_calls_out_stubbed_repair_boundary_and_milestone7_pending():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Implemented in Milestone 7A" in readme
    assert "Implemented in Milestone 7B" in readme
    assert "Implemented in Milestone 8" in readme
    assert "Implemented in Milestone 9" in readme
    assert "bounded one-shot conductor-driven repair loop" in readme
    assert "global constraints > global memory > alias-local overlay > pair-local overlay" in readme
