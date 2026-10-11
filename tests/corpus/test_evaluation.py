"""Ground truth must independently prove approvals and survive deduplication."""
import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from pdf_to_ofx.application.convert import analyze_pdf
from pdf_to_ofx.corpus.batch import analyze_corpus, file_sha256
from pdf_to_ofx.corpus.manifest import CorpusEntry
from pdf_to_ofx.corpus.evaluation import evaluate
from pdf_to_ofx.corpus.report import aggregate_report, compare_reports


@pytest.fixture
def research(synthetic_pdf, tmp_path):
    # Authored from the public recipe, not captured from the engine's output.
    truth = {"schema_version": 1, "sha256": file_sha256(synthetic_pdf), "independently_verified": True,
             "evidence_kind": "synthetic_recipe", "expectation": "valid_statement",
             "statement": {"period_start": "2026-09-01", "period_end": "2026-09-05", "currency": "BRL",
                           "opening_balance": "1000.00", "closing_balance": "1365.00", "transactions": [
                               dict(date="2026-09-01", description="PIX RECEBIDO EMPRESA TESTE", amount="500.00", balance_after=None),
                               dict(date="2026-09-02", description="TARIFA BANCARIA", amount="-35.00", balance_after=None),
                               dict(date="2026-09-03", description="PAGAMENTO FORNECEDOR TESTE", amount="-200.00", balance_after=None),
                               dict(date="2026-09-05", description="PIX RECEBIDO CLIENTE DEMO", amount="100.00", balance_after=None)]}}
    path = tmp_path / "truth.json"
    path.write_text(json.dumps(truth), encoding="utf-8")
    entry = dict(schema_version=2, local_path=str(synthetic_pdf), dataset="development", ground_truth_path="truth.json",
                 structural_family="signed-no-running", authorization="synthetic only", observed_features=["cd_markers"])
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(entry)+"\n", encoding="utf-8")
    return manifest, path, entry, truth


def test_verified_correctness_not_status_alone(research, tmp_path):
    manifest, path, entry, truth = research
    output = tmp_path / "run.jsonl"
    analyze_corpus(manifest, output)
    result = aggregate_report(output)["evaluation"]
    assert result["classifications"]["correct_approval"] == 1
    assert result["approval_precision"] == result["correct_coverage"] == 1
    truth["statement"]["transactions"][0]["description"] = "INDEPENDENT DIFFERENCE"
    path.write_text(json.dumps(truth), encoding="utf-8")
    analyze_corpus(manifest, output)
    assert aggregate_report(output)["evaluation"]["critical_false_approvals"] == 1
    assert "INDEPENDENT DIFFERENCE" not in output.read_text(encoding="utf-8")


def test_missing_or_unverified_truth_does_not_invent_metrics(research, tmp_path):
    manifest, path, entry, truth = research
    truth["independently_verified"] = False
    path.write_text(json.dumps(truth), encoding="utf-8")
    output = tmp_path / "run.jsonl"
    analyze_corpus(manifest, output)
    result = aggregate_report(output)["evaluation"]
    assert result["approval_precision"] is result["correct_coverage"] is None
    assert result["classifications"]["unverified"] == 1


def test_exact_and_family_split_leakage_not_hidden_by_dedup(research, tmp_path):
    manifest, _, entry, _ = research
    duplicate = dict(entry, dataset="evaluation")
    manifest.write_text(json.dumps(entry)+"\n"+json.dumps(duplicate)+"\n", encoding="utf-8")
    output = tmp_path / "run.jsonl"
    summary = analyze_corpus(manifest, output)
    assert summary.duplicates == 1
    result = aggregate_report(output)["evaluation"]
    assert result["exact_split_leaks"] == result["declared_family_split_leaks"] == 1
    assert result["classifications"]["correct_approval"] == 1
    assert result["by_dataset"]["development"]["approval_precision"] is None
    assert result["by_dataset"]["evaluation"]["approval_precision"] is None


def test_false_rejection_correct_rejection_and_out_of_scope(research, tmp_path):
    manifest, path, entry, truth = research
    output = tmp_path / "run.jsonl"
    analysis = analyze_pdf(__import__("pathlib").Path(entry["local_path"]))
    from pdf_to_ofx.domain.evidence import AnalysisStatus
    with patch("pdf_to_ofx.corpus.batch.analyze_pdf", return_value=replace(analysis, status=AnalysisStatus.UNSUPPORTED, statement=None)):
        analyze_corpus(manifest, output)
    assert aggregate_report(output)["evaluation"]["classifications"]["false_rejection"] == 1
    truth.pop("statement")
    truth["expectation"] = "insufficient_evidence"
    path.write_text(json.dumps(truth), encoding="utf-8")
    with patch("pdf_to_ofx.corpus.batch.analyze_pdf", return_value=replace(analysis, status=AnalysisStatus.INVALID, statement=None)):
        analyze_corpus(manifest, output)
    assert aggregate_report(output)["evaluation"]["classifications"]["correct_rejection"] == 1
    truth["expectation"] = "out_of_scope"
    path.write_text(json.dumps(truth), encoding="utf-8")
    analyze_corpus(manifest, output)
    assert aggregate_report(output)["evaluation"]["classifications"]["out_of_scope"] == 1


def test_regression_comparison_uses_shared_documents(research, tmp_path):
    manifest, path, _, truth = research
    first, second = tmp_path/"a.jsonl", tmp_path/"b.jsonl"
    analyze_corpus(manifest, first)
    truth["statement"]["closing_balance"] = "1366.00"
    path.write_text(json.dumps(truth), encoding="utf-8")
    analyze_corpus(manifest, second)
    diff = compare_reports(second, first)
    assert diff["shared_documents"] == diff["lost_correct_approvals"] == diff["new_false_approvals"] == 1


@pytest.mark.parametrize("fields", [{"dataset": "unknown"}, {"observed_features": "text"}, {"observed_features": [1]}])
def test_v2_rejects_invalid_metadata(fields):
    with pytest.raises(ValueError):
        CorpusEntry.from_dict(dict(schema_version=2, dataset="development", **{k:v for k,v in fields.items() if k != "dataset"}) if "dataset" not in fields else dict(schema_version=2, **fields))


def test_report_never_replaces_independent_truth(research):
    manifest, path, entry, truth = research
    target = path.with_suffix(".jsonl")
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    entry["ground_truth_path"] = target.name
    manifest.write_text(json.dumps(entry)+"\n", encoding="utf-8")
    before = target.read_bytes()
    with pytest.raises(ValueError):
        analyze_corpus(manifest, target)
    assert target.read_bytes() == before


def test_conflicting_truth_cannot_hide_critical_false_approval(research, tmp_path):
    manifest, path, entry, truth = research
    other = path.with_name("other.json")
    truth["statement"]["transactions"][0]["description"] = "A DIFFERENT INDEPENDENT CLAIM"
    other.write_text(json.dumps(truth), encoding="utf-8")
    manifest.write_text(json.dumps(entry)+"\n"+json.dumps(dict(entry,ground_truth_path=other.name))+"\n",encoding="utf-8")
    output = tmp_path/"run.jsonl"
    analyze_corpus(manifest, output)
    evaluation = aggregate_report(output)["evaluation"]
    assert evaluation["classifications"]["unverified"] == 1
    assert evaluation["truth_errors"]["conflicting_truth"] == 1
    assert evaluation["critical_false_approvals"] == 1
    assert evaluation["approval_precision"] is None


@pytest.mark.parametrize("field,value", [("classification", ["PRIVATE SENTINEL"]), ("dataset", ["PRIVATE SENTINEL"]),
                                          ("family_hash", "PRIVATE SENTINEL"), ("truth_error", "PRIVATE SENTINEL")])
def test_untrusted_evaluation_labels_are_never_rendered(research, tmp_path, field, value):
    manifest, _, _, _ = research
    output = tmp_path/"run.jsonl"
    analyze_corpus(manifest,output)
    row = json.loads(output.read_text(encoding="utf-8"))
    row["evaluation"][field] = value
    output.write_text(json.dumps(row)+"\n",encoding="utf-8")
    report = aggregate_report(output)
    assert report["input_errors"] == {"report_invalid": 1}
    assert "PRIVATE SENTINEL" not in json.dumps(report)
