from unittest.mock import patch
from pdf_to_ofx.application.csv_export import export_csv_analysis


def test_gui_csv_save_and_file_switch(window, synthetic_pdf, tmp_path):
    window.load_pdf(synthetic_pdf)
    assert window.csv_button.isEnabled()
    output = tmp_path / "chosen.csv"
    with patch("pdf_to_ofx.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(output), "")):
        window.csv_button.click()
        assert output.read_bytes() == export_csv_analysis(window.analysis).encode("utf-8")
        window.csv_button.click()
        assert "já existe" in window.status_label.text()
    window.load_pdf(synthetic_pdf.with_suffix(".txt"))
    assert not window.csv_button.isEnabled()
    with patch("pdf_to_ofx.ui.main_window.QFileDialog.getSaveFileName") as dialog:
        window.save_csv()
        dialog.assert_not_called()


def test_csv_without_ofx_metadata_and_retryable_write_error(window, write_pdf, tmp_path):
    pdf = tmp_path/"generic.pdf"
    write_pdf("Período: 01/01/2029 a 31/01/2029\nSaldo inicial: R$ 100,00\nSaldo final: R$ 110,00\n02/01/2029 FICTICIO +R$ 10,00", pdf)
    window.load_pdf(pdf)
    assert window.csv_button.isEnabled() and not window.save_button.isEnabled()
    destination = tmp_path/"absent"/"output.csv"
    with patch("pdf_to_ofx.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
        window.save_csv()
    assert not destination.exists()
    assert "Não foi possível salvar" in window.status_label.text()
    assert window.csv_button.isEnabled()
    with patch("pdf_to_ofx.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(tmp_path/"out.pdf"), "")):
        window.save_csv()
    assert "extensão .csv" in window.status_label.text()
