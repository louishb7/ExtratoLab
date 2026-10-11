"""Financial evidence, source fidelity and worker race regressions."""
from dataclasses import replace
from threading import Event
from unittest.mock import patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdf_to_ofx.application.convert import analyze_pdf
from pdf_to_ofx.application.review import ReviewSession
from pdf_to_ofx.domain.evidence import EvidenceReport, EvidenceStatus, SourceSpan
from pdf_to_ofx.pdf.sources import source_tokens
from tests.ui.waiting import wait_for_analysis


@pytest.mark.parametrize("fixture", ["synthetic_pdf", "inter_pdf"])
def test_all_sources_match_original_tokens(request, fixture):
    analysis = analyze_pdf(request.getfixturevalue(fixture))
    session = ReviewSession(analysis)
    for source in analysis.provenance.transactions:
        assert session.transaction_source(source.transaction_index) is source
        for span in (*source.spans, *source.description_sources, source.date_source,
                     source.amount_source, source.direction_source):
            assert session.resolve(span).tokens == source_tokens(analysis.document, span, analysis.layout_profile.tolerances)
    assert session.resolve(SourceSpan(99, 1, 0, 1)).tokens is None


def test_selection_uses_cached_sources_and_clears_on_file_change(window, synthetic_pdf, inter_pdf, capsys):
    window.load_pdf(synthetic_pdf)
    with patch("pdf_to_ofx.pdf.extractor.extract_pdf", side_effect=AssertionError("No extraction on selection")):
        window.table.selectRow(0)
        first = window.details.toPlainText()
        assert window.analysis.statement.transactions[0].description in first
        assert "Página" in first
        window.table.selectRow(1)
        assert window.details.toPlainText() != first
    window.load_pdf(inter_pdf)
    assert "Selecione" in window.details.toPlainText()
    assert window.review_session is not None
    window.load_pdf(inter_pdf.with_suffix(".txt"))
    assert window.review_session is None
    assert "Selecione" in window.details.toPlainText()
    assert capsys.readouterr().out == ""


def test_missing_field_source_is_explicit(window, synthetic_pdf):
    analysis = analyze_pdf(synthetic_pdf)
    sources = (replace(analysis.provenance.transactions[0], date_source=None), *analysis.provenance.transactions[1:])
    analysis = replace(analysis, provenance=replace(analysis.provenance, transactions=sources))
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", return_value=analysis):
        window.load_pdf(synthetic_pdf)
    window.table.selectRow(0)
    assert "Evidência individual não disponível" in window.details.toPlainText()
    assert not window.save_button.isEnabled()


def test_no_false_running_balance_message_and_no_assumed_currency(window, synthetic_pdf):
    analysis = analyze_pdf(synthetic_pdf)
    evidence = replace(analysis.evidence, opening_closing_reconciled=EvidenceStatus.NOT_AVAILABLE,
                       running_balance_verified=EvidenceStatus.NOT_APPLICABLE,
                       credit_total_verified=EvidenceStatus.VERIFIED, debit_total_verified=EvidenceStatus.VERIFIED)
    analysis = replace(analysis, evidence=evidence, statement=replace(analysis.statement, currency=None))
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", return_value=analysis):
        window.load_pdf(synthetic_pdf)
    assert "Saldos progressivos verificados" not in window.summary_labels["validation"].text()
    assert "Saldos progressivos: Não aplicável" in window.diagnostics.toPlainText()
    assert "R$" not in window.table.item(0, 3).text()
    assert "Não resolvida" in window.currency_label.text()


def test_slow_worker_keeps_event_loop_alive_and_discards_stale_result(window, synthetic_pdf, inter_pdf):
    entered, release = Event(), Event()
    old, new = analyze_pdf(synthetic_pdf), analyze_pdf(inter_pdf)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(2)
    def analyzer(path):
        if path == synthetic_pdf:
            entered.set()
            assert release.wait(5)
            return old
        return new
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", side_effect=analyzer):
        window.load_pdf(synthetic_pdf, background=True)
        assert entered.wait(2)
        window.load_pdf(inter_pdf, background=True)
        QTest.qWait(25)
        QApplication.processEvents()
        assert ticks and window.table.rowCount() == 0
        assert not window.save_button.isEnabled()
        release.set()
        wait_for_analysis(window)
    timer.stop()
    assert window.analysis == new
    assert window.selected_file == inter_pdf
    assert window.table.rowCount() == 5


def test_invalid_selection_discards_pending_worker(window, synthetic_pdf):
    entered, release = Event(), Event()
    result = analyze_pdf(synthetic_pdf)
    def analyzer(_):
        entered.set()
        assert release.wait(5)
        return result
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", side_effect=analyzer):
        window.load_pdf(synthetic_pdf, background=True)
        assert entered.wait(2)
        window.load_pdf(synthetic_pdf.with_suffix(".txt"), background=True)
        release.set()
        wait_for_analysis(window)
    assert window.analysis is None
    assert window.table.rowCount() == 0
    assert not window.save_button.isEnabled()


def test_wrapped_description_sources_are_resolved_once(window, tmp_path):
    from tests.fixtures.international.generate import generate
    manifest = generate(tmp_path/"corpus")
    window.load_pdf(manifest.parent/"unsigned-flow-subtotals.pdf")
    window.table.selectRow(0)
    text = window.details.toPlainText()
    assert "ITEM ALFA DEMO" in text
    assert "Sinal do subtotal" in text
    analysis = window.analysis
    session = ReviewSession(replace(analysis, document=None))
    assert session.resolve(analysis.provenance.transactions[0].amount_source).tokens is None


def test_close_while_worker_runs_defers_destruction(window, synthetic_pdf):
    entered, release = Event(), Event()
    result = analyze_pdf(synthetic_pdf)
    def analyzer(_):
        entered.set()
        assert release.wait(5)
        return result
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", side_effect=analyzer):
        window.load_pdf(synthetic_pdf, background=True)
        assert entered.wait(2)
        window.close()
        assert window._closing and window.isVisible()
        release.set()
        wait_for_analysis(window)
    assert not window.isVisible()
    assert window.analysis is None


def test_real_multiline_description_evidence_in_gui(window, tmp_path):
    from pathlib import Path
    from tests.fixtures.layouts.generate import write_layout_pdf
    from pdf_to_ofx.domain.evidence import AnalysisStatus
    recipe = Path(__file__).parents[1]/"fixtures"/"layouts"/"wrapped_description_separators"/"pages.json"
    pdf = tmp_path/"multiline.pdf"
    write_layout_pdf(recipe,pdf)
    window.load_pdf(pdf)
    assert window.analysis.status == AnalysisStatus.SUCCESS
    source = window.analysis.provenance.transactions[0]
    assert len({(s.page,s.row) for s in source.description_sources}) > 1
    window.table.selectRow(0)
    assert "COMPLEMENTO FICTICIO" in window.details.toPlainText()
    for span in source.description_sources:
        tokens = window.review_session.resolve(span).tokens
        assert tokens == source_tokens(window.analysis.document, span, window.analysis.layout_profile.tolerances)


def test_minimum_window_keeps_summary_and_export_form_usable(window, synthetic_pdf, qapp):
    window.load_pdf(synthetic_pdf)
    window.resize(900,680)
    qapp.processEvents()
    assert window.width() >= 1000 and window.height() >= 800
    assert window.summary_labels["bank"].height() >= 40
    assert all(field.minimumHeight() >= 30 for field in window.metadata_fields.values())


def test_display_totals_never_round_under_restricted_decimal_context(window, synthetic_pdf):
    from decimal import localcontext
    analysis = analyze_pdf(synthetic_pdf)
    with patch("pdf_to_ofx.ui.main_window.analyze_pdf", return_value=analysis):
        with localcontext() as context:
            context.prec = 2
            window.load_pdf(synthetic_pdf)
    assert "600,00" in window.totals_label.text()
    assert "-235,00" in window.totals_label.text()


def test_financial_contradiction_has_actionable_diagnosis():
    from pdf_to_ofx.application.convert import StatementAnalysis
    from pdf_to_ofx.domain.evidence import AnalysisStatus
    from pdf_to_ofx.ui.presentation import diagnostic_text
    message = diagnostic_text(StatementAnalysis(AnalysisStatus.INVALID,
                                                blocking_capabilities=("checkpoint_reconciliation",)))
    assert "saldos de controle" in message and "soma dos lançamentos" in message
    assert "capacidade estrutural necessária ainda está ausente" not in message
