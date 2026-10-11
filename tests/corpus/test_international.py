"""Twelve real structural experiments, not a claim about twelve banks."""
import json
from pathlib import Path

from pdf_to_ofx.corpus.batch import analyze_corpus
from pdf_to_ofx.corpus.report import aggregate_report, compare_reports
from tests.fixtures.international.generate import generate


def test_international_expectations_are_independent_and_reproducible(tmp_path):
    one, two = tmp_path/"one", tmp_path/"two"
    manifest = generate(one)
    generate(two)
    for path in one.iterdir():
        assert path.read_bytes() == (two/path.name).read_bytes()
    a, b = tmp_path/"a.jsonl", tmp_path/"b.jsonl"
    summary = analyze_corpus(manifest, a)
    analyze_corpus(manifest, b)
    assert summary.entries == summary.analyzed == 12
    assert summary.duplicates == summary.input_errors == 0
    result = aggregate_report(a)
    evaluation = result["evaluation"]
    assert evaluation["critical_false_approvals"] == 0
    assert evaluation["truth_errors"] == {}
    assert evaluation["classifications"] == dict(correct_approval=8, false_rejection=0, correct_rejection=4,
                                                   incorrect_approval=0, out_of_scope=0, unverified=0)
    assert evaluation["approval_precision"] == 1
    assert evaluation["correct_coverage"] == 8/8
    assert evaluation["exact_split_leaks"] == evaluation["declared_family_split_leaks"] == 0
    assert evaluation["unique_declared_families"] == 12
    assert evaluation["by_dataset"]["development"]["correct_coverage"] == 6/6
    assert evaluation["by_dataset"]["evaluation"]["correct_coverage"] == 2/2
    comparison = compare_reports(b,a)
    assert comparison["new_correct_approvals"] == comparison["lost_correct_approvals"] == comparison["new_false_approvals"] == 0
    assert comparison["new_failure_clusters"] == []
    for record in a.read_text(encoding="utf-8").splitlines():
        assert "ALFA FICTICIO" not in record and "ground_truth_path" not in record


def test_adversarial_population_rejects_without_changing_original_expectations(tmp_path):
    recipe = Path(__file__).parents[1] / "fixtures/international/adversarial.json"
    manifest = generate(tmp_path / "adversarial", cases_path=recipe)
    output = tmp_path / "report.jsonl"
    summary = analyze_corpus(manifest, output)
    assert summary.entries == summary.analyzed == 9
    report = aggregate_report(output)
    assert report["evaluation"]["classifications"] == dict(correct_approval=0, false_rejection=0, correct_rejection=9,
        incorrect_approval=0, out_of_scope=0, unverified=0)
    assert report["evaluation"]["critical_false_approvals"] == 0
    assert report["evaluation"]["truth_errors"] == {}
