"""Review/export session and smaller logical viewports with fictitious data."""
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from pdf_to_ofx.domain.evidence import AnalysisStatus
from tests.fixtures.international.generate import generate


@pytest.mark.parametrize('width,height', [(1366,768), (1092,614), (1280,720), (900,600)])
def test_smaller_logical_viewports_keep_controls_reachable(window, qapp, tmp_path, width, height):
    manifest = generate(tmp_path / 'fixtures')
    window.load_pdf(manifest.parent / 'separate-debit-credit-columns.pdf')
    window.resize(width, height)
    qapp.processEvents()
    assert (window.width(), window.height()) == (width, height)
    assert window.analysis.status == AnalysisStatus.SUCCESS
    assert window.summary_labels['bank'].text() == window.analysis.bank_name
    assert window.analysis.statement.layout_id not in window.summary_labels['bank'].text()
    assert all('Athenas' not in label.text() for label in window.findChildren(QLabel))
    window.tabs.setCurrentIndex(2)
    window.content_scroll.ensureWidgetVisible(window.tabs)
    qapp.processEvents()
    inner = window.tabs.widget(2)
    for field in window.metadata_fields.values():
        inner.ensureWidgetVisible(field)
        field.setFocus()
        qapp.processEvents()
        center = field.mapTo(inner.viewport(), field.rect().center())
        assert inner.viewport().rect().contains(center)
        assert field.hasFocus()
    window.content_scroll.ensureWidgetVisible(window.save_button)
    qapp.processEvents()
    center = window.save_button.mapTo(window.content_scroll.viewport(), window.save_button.rect().center())
    assert window.content_scroll.viewport().rect().contains(center)


def test_integrated_fictitious_review_export_overwrite_and_clear(window, qapp, tmp_path):
    manifest = generate(tmp_path / 'fixtures')
    window.load_pdf(manifest.parent / 'separate-debit-credit-columns.pdf')
    assert window.analysis.status == AnalysisStatus.SUCCESS
    assert window.csv_button.isEnabled() and not window.save_button.isEnabled()
    window.table.setFocus()
    window.table.selectRow(0)
    QTest.keyClick(window.table, Qt.Key.Key_Down)
    qapp.processEvents()
    assert window.table.currentRow() == 1
    assert 'Cabeçalho da coluna' in window.details.toPlainText()
    window.tabs.setCurrentIndex(1)
    assert 'Verificado' in window.diagnostics.toPlainText()
    window.tabs.setCurrentIndex(2)
    for key,value in dict(organization='Fictitious', institution_id='999', bank_id='999',
                          branch_id='DEMO', account_id='DEMO-1').items():
        window.metadata_fields[key].setText(value)
    assert window.save_button.isEnabled()
    for method, suffix in [(window.save_ofx,'.ofx'), (window.save_csv,'.csv')]:
        path = tmp_path / ('result' + suffix)
        with patch('pdf_to_ofx.ui.main_window.QFileDialog.getSaveFileName', return_value=(str(path),'')):
            method()
            original = path.read_bytes()
            assert original
            method()
            assert 'já existe' in window.status_label.text()
            assert path.read_bytes() == original
    window.load_pdf(manifest.parent / 'missing-period.pdf')
    assert window.analysis.status != AnalysisStatus.SUCCESS
    assert window.table.rowCount() == 0
    assert all(not field.text() for field in window.metadata_fields.values())
    assert not window.save_button.isEnabled() and not window.csv_button.isEnabled()
    assert 'BETA FICTICIO' not in window.details.toPlainText()


def test_long_descriptions_and_extensive_evidence_scroll_without_losing_text(window, qapp, synthetic_pdf):
    from dataclasses import replace
    from pdf_to_ofx.application.convert import analyze_pdf
    analysis = analyze_pdf(synthetic_pdf)
    description = 'REFERÊNCIA INTEIRAMENTE FICTÍCIA ' * 40
    transactions = (replace(analysis.statement.transactions[0], description=description), *analysis.statement.transactions[1:])
    presentation = replace(analysis, statement=replace(analysis.statement, transactions=transactions))
    with patch('pdf_to_ofx.ui.main_window.analyze_pdf', return_value=presentation):
        window.load_pdf(synthetic_pdf)
    window.resize(900,600)
    window.table.selectRow(0)
    window.details_button.setChecked(True)
    window.technical_button.setChecked(True)
    qapp.processEvents()
    assert window.table.item(0,1).toolTip() == description
    assert description in window.details.toPlainText()
    assert window.details.verticalScrollBar().maximum() > 0
    assert window.table.verticalScrollBar().maximum() > 0
