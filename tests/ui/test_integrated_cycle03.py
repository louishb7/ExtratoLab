"""A conversion-first UI retains evidence on demand without changing finance."""
from unittest.mock import patch

from pdf_to_ofx.pdf.sources import source_tokens


def test_table_is_primary_and_original_text_is_session_cached(window,qapp,synthetic_pdf):
    window.load_pdf(synthetic_pdf)
    assert not window.tabs.isVisible()
    assert 'SUCCESS' not in window.analysis_status_label.text()
    with patch('pdf_to_ofx.pdf.extractor.extract_pdf',side_effect=AssertionError('Selection must use session cache')):
        window.table.selectRow(0)
        assert not window.details.isVisible()
        window.details_button.click()
        qapp.processEvents()
        assert window.source_context.isVisible()
        assert 'tokens' not in window.source_context.toPlainText()
        source=window.analysis.provenance.transactions[0]
        for span in (source.date_source,source.amount_source):
            assert ' '.join(source_tokens(window.analysis.document,span)) in window.source_context.toPlainText()
        window.technical_button.click()
        qapp.processEvents()
        assert window.details.isVisible()
        assert 'Página' in window.details.toPlainText()
    window.table.clearSelection()
    assert 'Selecione' in window.source_context.toPlainText()


def test_context_and_details_are_cleared_for_next_document(window,synthetic_pdf,inter_pdf):
    window.load_pdf(synthetic_pdf)
    window.table.selectRow(0)
    window.details_button.setChecked(True)
    window.technical_button.setChecked(True)
    window.load_pdf(inter_pdf)
    assert not window.tabs.isVisible()
    assert not window.technical_button.isChecked()
    assert 'Selecione' in window.source_context.toPlainText()
    assert window.save_button.isEnabled() and window.csv_button.isEnabled()
    assert not window.metadata_group.isVisible()


def test_account_type_caption_keeps_ofx_enum(window, synthetic_pdf):
    window.load_pdf(synthetic_pdf)
    window.account_type.setCurrentIndex(1)
    assert window.account_type.currentText() == 'Poupança'
    assert window.export_metadata.account_type == 'SAVINGS'
