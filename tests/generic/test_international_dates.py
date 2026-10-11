"""Calendar evidence selects one document convention, never locale or totals."""
from datetime import date
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.pdf.sources import source_tokens


def document(make_document, period, first, second, labels=('Opening balance', 'Closing balance')):
    return make_document(f'{period}\n{labels[0]}: EUR 100,00\n{labels[1]}: EUR 105,00\n'
        f'{first} ALFA +EUR 10,00\n{second} BETA -EUR 5,00')


@pytest.mark.parametrize('period,first,second,labels', [
    ('Statement period: 01/01/2029 to 01/31/2029', '01/02/2029', '01/03/2029', ('Opening balance', 'Closing balance')),
    ('Statement period: 01/01/2029 to 31/01/2029', '02/01/2029', '03/01/2029', ('Opening balance', 'Closing balance')),
    ('Période: 2029-01-01 au 2029-01-31', '2029-01-02', '2029-01-03', ('Solde initial', 'Solde final')),
])
def test_calendar_proof_and_iso_keep_sources(make_document, period, first, second, labels):
    doc = document(make_document, period, first, second, labels)
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    statement = result.interpretation.statement
    assert (statement.period_start, statement.period_end) == (date(2029,1,1), date(2029,1,31))
    assert [t.posting_date for t in statement.transactions] == [date(2029,1,2), date(2029,1,3)]
    assert [t.amount for t in statement.transactions] == [Decimal('10'), Decimal('-5')]
    assert source_tokens(doc, result.interpretation.provenance.transactions[0].date_source) == (first,)


@pytest.mark.parametrize('period', [
    'Statement period: 03/04/2029 to 05/06/2029',
    'Statement period: 01/01/2029 to 12/12/2029',
    'Statement period: 01/01/2029 to 2029-01-31',
    'Période: 2029-02-30 au 2029-03-31',
    'Période: 2029-03-31 au 2029-01-01',
])
def test_concurrent_or_invalid_periods_cannot_choose_dates_for_reconciliation(make_document, period):
    result = infer_layout(document(make_document, period, '03/04/2029', '05/04/2029'))
    assert result.status == AnalysisStatus.UNSUPPORTED
    assert 'date_convention_ambiguous' in result.blocking_capabilities
    assert result.interpretation is None


@pytest.mark.parametrize('first,second', [('02/01/2029','02/02/2029'), ('01/32/2029','01/03/2029')])
def test_outside_period_or_invalid_movement_is_never_redated(make_document, first, second):
    result = infer_layout(document(make_document, 'Statement period: 01/01/2029 to 01/31/2029', first, second))
    assert result.status != AnalysisStatus.SUCCESS
    assert result.interpretation is None


def test_conflicting_document_conventions_abstain(make_document):
    doc = document(make_document, 'Período: 01/01/2029 a 31/01/2029\n'
        'Statement period: 01/01/2029 to 01/31/2029', '01/02/2029', '01/03/2029')
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS


def test_booking_and_value_dates_without_distinct_owners_remain_blocked(make_document):
    doc = document(make_document, 'Période: 2029-01-01 au 2029-01-31',
        '2029-01-02 2029-01-04', '2029-01-03 2029-01-05')
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS
