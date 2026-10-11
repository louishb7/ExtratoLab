"""Explicit session-only identity cannot override financial approval."""
from dataclasses import replace
from unittest.mock import patch

import pytest

from pdf_to_ofx.application.convert import analyze_pdf, export_analysis
from pdf_to_ofx.domain.evidence import AnalysisStatus


@pytest.fixture
def generic_pdf(write_pdf, tmp_path):
    path = tmp_path / "generic.pdf"
    write_pdf("Período: 01/03/2027 a 03/03/2027\nSaldo inicial: R$ 100,00\nSaldo final: R$ 100,01\n"
              "01/03/2027 ALFA +R$ 0,02 R$ 100,02\n02/03/2027 BETA -R$ 0,01 R$ 100,01", path)
    return path


def fill(window):
    for key, value in dict(organization="Fictitious", institution_id="999", bank_id="999",
                           branch_id="DEMO", account_id="DEMO-1").items():
        window.metadata_fields[key].setText(value)


def test_metadata_complete_enables_same_exporter_and_clears_on_file_change(window, generic_pdf, synthetic_pdf):
    window.load_pdf(generic_pdf)
    original = window.analysis.statement
    window.tabs.setCurrentIndex(2)
    assert window.metadata_group.isVisible()
    assert not window.save_button.isEnabled()
    fill(window)
    assert window.save_button.isEnabled()
    assert window.analysis.statement is original
    assert window.conversion_result.ofx == export_analysis(window.analysis, window.export_metadata)
    assert export_analysis(window.analysis, window.export_metadata) == window.conversion_result.ofx
    window.metadata_fields["account_id"].clear()
    assert not window.save_button.isEnabled()
    window.load_pdf(synthetic_pdf)
    assert window.export_metadata is None
    assert all(not f.text() for f in window.metadata_fields.values())
    assert window.save_button.isEnabled()


def test_metadata_cannot_override_established_account(window, inter_pdf):
    window.load_pdf(inter_pdf)
    fill(window)
    assert not window.save_button.isEnabled()
    assert window.conversion_result is None


@pytest.mark.parametrize("status", [AnalysisStatus.INVALID, AnalysisStatus.UNSUPPORTED, AnalysisStatus.AMBIGUOUS])
def test_metadata_cannot_approve_rejected_analysis(window, generic_pdf, status):
    rejected = replace(analyze_pdf(generic_pdf), status=status)
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", return_value=rejected):
        window.load_pdf(generic_pdf)
    fill(window)
    assert not window.save_button.isEnabled()
    assert window.conversion_result is None


def test_metadata_cannot_supply_missing_balance_or_currency(window, generic_pdf):
    analysis = analyze_pdf(generic_pdf)
    for field in ("closing_balance", "currency"):
        incomplete = replace(analysis, statement=replace(analysis.statement, **{field: None}))
        with patch("pdf_to_ofx.ui.main_window.analyze_pdf", return_value=incomplete):
            window.load_pdf(generic_pdf)
        fill(window)
        assert not window.save_button.isEnabled()
