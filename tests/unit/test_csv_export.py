"""CSV semantic, serialization and safe-publication contracts."""
import csv
from dataclasses import replace
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest

from pdf_to_ofx.application.convert import analyze_pdf
from pdf_to_ofx.application.csv_export import export_csv_analysis, assess_csv_readiness
from pdf_to_ofx.application.export import write_csv
from pdf_to_ofx.domain.errors import ConversionError
from pdf_to_ofx.domain.evidence import AnalysisStatus, EvidenceReport
from pdf_to_ofx.tabular.csv import HEADERS, generate_csv


@pytest.mark.parametrize("description", ['João, "fictício"\nsegunda linha', '=SUM(A1)', '+1+1', '-1+1', '@SUM(A1)',
                                          '  =1+1', '\tformula', '\rformula', '\nformula'])
def test_unicode_quoting_and_formula_protection(synthetic_pdf, description):
    analysis = analyze_pdf(synthetic_pdf)
    transactions = (replace(analysis.statement.transactions[0], description=description), *analysis.statement.transactions[1:])
    statement = replace(analysis.statement, transactions=transactions)
    a = generate_csv(statement)
    assert a.encode("utf-8") == generate_csv(statement).encode("utf-8")
    rows = list(csv.reader(StringIO(a)))
    assert tuple(rows[0]) == HEADERS
    assert rows[1][1] == (description if description.startswith("João") else "'" + description)
    assert statement.transactions[0].description == description
    assert rows[1][0] == "2026-09-01"
    assert rows[1][2:5] == ["credit", "500.00", "BRL"]
    assert rows[2][2:4] == ["debit", "-35.00"]


def test_csv_requires_no_ofx_metadata_or_closing_balance(inter_pdf):
    analysis = analyze_pdf(inter_pdf)
    statement = replace(analysis.statement, closing_balance=None, account=None)
    analysis = replace(analysis, statement=statement)
    assert "1000.00" in export_csv_analysis(analysis)
    rows = list(csv.reader(StringIO(export_csv_analysis(replace(analysis, statement=replace(statement, currency=None))))))
    assert rows[1][4] == ""
    assert rows[1][5] != ""



@pytest.mark.parametrize("status", [AnalysisStatus.AMBIGUOUS, AnalysisStatus.INVALID, AnalysisStatus.UNSUPPORTED])
def test_rejected_analysis_never_exports(synthetic_pdf, status):
    analysis = replace(analyze_pdf(synthetic_pdf), status=status)
    with pytest.raises(ConversionError):
        export_csv_analysis(analysis)
    assert assess_csv_readiness(analysis).issues == ("analysis_not_approved",)


def test_missing_evidence_or_invalid_financial_data_never_exports(synthetic_pdf):
    analysis = analyze_pdf(synthetic_pdf)
    for invalid in (replace(analysis, evidence=EvidenceReport()),
                    replace(analysis, statement=replace(analysis.statement, closing_balance=Decimal("1")))):
        with pytest.raises(ConversionError):
            export_csv_analysis(invalid)


def test_publication_never_overwrites_and_cleans_errors(tmp_path):
    output = tmp_path / "out.csv"
    write_csv(output, "João\n")
    assert output.read_bytes() == "João\n".encode("utf-8")
    with pytest.raises(FileExistsError):
        write_csv(output, "new")
    assert output.read_bytes() == "João\n".encode("utf-8")
    output.unlink()
    with patch("pdf_to_ofx.application.export.os.fsync", side_effect=OSError("sentinel")):
        with pytest.raises(OSError):
            write_csv(output, "not partial")
    assert list(tmp_path.iterdir()) == []
    with patch("pdf_to_ofx.application.export.Path.hardlink_to", side_effect=OSError("sentinel")):
        with pytest.raises(OSError):
            write_csv(output, "not partial")
    assert list(tmp_path.iterdir()) == []
