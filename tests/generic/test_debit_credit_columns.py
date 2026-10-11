"""Column direction must follow explicit captions and complete geometric cells."""
from dataclasses import replace
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.pdf.sources import source_tokens
from tests.generic.test_operators import positioned


HEADER = [[(35, 'Período: 01/01/2029 a 31/01/2029')],
          [(35, 'Saldo inicial: R$ 100,00')], [(35, 'Saldo final: R$ 105,00')]]
COLUMNS = [(35, 'Data'), (130, 'Descrição'), (340, 'Débito'), (450, 'Crédito')]
MOVEMENTS = [[(35, '02/01/2029'), (130, 'ALFA'), (450, 'R$ 10,00')],
             [(35, '03/01/2029'), (130, 'BETA'), (340, 'R$ 5,00')]]


def test_declared_columns_prove_sign_and_header_source_under_translation():
    doc = positioned(HEADER + [COLUMNS] + MOVEMENTS)
    for offset in (0, 57):
        translated = replace(doc, pages=tuple(replace(page, words=tuple(
            replace(word, x0=word.x0 + offset, x1=word.x1 + offset) for word in page.words)) for page in doc.pages))
        result = infer_layout(translated)
        assert result.status == AnalysisStatus.SUCCESS
        assert [t.amount for t in result.interpretation.statement.transactions] == [Decimal('10'), Decimal('-5')]
        for field, label in zip(result.interpretation.provenance.transactions, ['Crédito', 'Débito']):
            assert field.direction_basis == 'debit_credit_column'
            assert source_tokens(translated, field.direction_source) == (label,)


def test_independent_balance_column_and_repeated_headers():
    columns = COLUMNS + [(570, 'Saldo')]
    first = MOVEMENTS[0] + [(570, 'R$ 110,00')]
    second = MOVEMENTS[1] + [(570, 'R$ 105,00')]
    doc = positioned(HEADER + [columns, first], [columns, second])
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    assert [t.balance_after for t in result.interpretation.statement.transactions] == [Decimal('110'), Decimal('105')]
    assert result.interpretation.evidence.financial_coverage_verified.value == 'verified'


@pytest.mark.parametrize('columns,rows', [
    (COLUMNS[:-1], MOVEMENTS),
    (COLUMNS[:-1] + [(450, 'Débito')], MOVEMENTS),
    (COLUMNS, [MOVEMENTS[0] + [(340, 'R$ 0,00')], MOVEMENTS[1]]),
    (COLUMNS, [[(35,'02/01/2029'), (130,'ALFA'), (395,'R$ 10,00')], MOVEMENTS[1]]),
    (COLUMNS, [MOVEMENTS[0], [(35,'03/01/2029'), (130,'BETA'), (340,'+R$ 5,00')]]),
])
def test_missing_conflicting_dual_or_unowned_columns_abstain(columns, rows):
    result = infer_layout(positioned(HEADER + [columns] + rows))
    assert result.status != AnalysisStatus.SUCCESS
    assert result.interpretation is None


def test_absent_header_cannot_invent_a_debit_to_reconcile():
    result = infer_layout(positioned(HEADER + MOVEMENTS))
    assert result.status != AnalysisStatus.SUCCESS


def test_repeated_header_conflict_or_missing_page_header_abstains():
    for second_page in ([COLUMNS[:2] + [(340,'Crédito'), (450,'Débito')], MOVEMENTS[1]], [MOVEMENTS[1]]):
        result = infer_layout(positioned(HEADER + [COLUMNS, MOVEMENTS[0]], second_page))
        assert result.status != AnalysisStatus.SUCCESS
        assert result.interpretation is None


def test_english_captions_have_same_structural_meaning():
    columns = [(35,'Date'), (130,'Description'), (340,'Debit'), (450,'Credit')]
    assert infer_layout(positioned(HEADER + [columns] + MOVEMENTS)).status == AnalysisStatus.SUCCESS


def test_late_header_cannot_mix_implicit_and_column_directions():
    doc = positioned(HEADER + [MOVEMENTS[0], COLUMNS, MOVEMENTS[1]])
    result = infer_layout(doc)
    assert result.status != AnalysisStatus.SUCCESS
    assert result.blocking_capabilities == ('column_ownership',)
