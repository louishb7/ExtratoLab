"""Isolate lexical convention from currency and financial ownership."""
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.generic.semantics import parse_money, scan_money_regions
from pdf_to_ofx.generic.structure import reconstruct_rows, Tolerances
from pdf_to_ofx.pdf.sources import source_tokens


@pytest.mark.parametrize('text,amount,currency', [
    ('EUR 1.234,56', '1234.56', 'EUR'), ('USD 1,234.56', '1234.56', 'USD'),
    ('EUR 1234.56', '1234.56', 'EUR'), ('USD 1234,56', '1234.56', 'USD'),
    ('-BRL 1,234.56', '-1234.56', 'BRL'), ('+EUR 0,01', '0.01', 'EUR'),
])
def test_unambiguous_cent_lexemes_preserve_currency_and_full_span(make_document, text, amount, currency):
    money = parse_money(text)
    assert money.amount == Decimal(amount)
    assert money.currency.code == currency
    row = reconstruct_rows(make_document(text))[0]
    scan = scan_money_regions(row, Tolerances())
    assert not scan.incomplete
    assert len(scan.regions) == 1
    assert (scan.regions[0].start, scan.regions[0].end) == (0, len(row.words))


@pytest.mark.parametrize('text', ['EUR 1.234', 'USD 1,234', '$ 1,234.56',
    'EUR 1.23,45', 'USD 1,23.45', 'EUR 1 234,56', 'USD 100.000',
    'EUR 1,234,56', 'USD 1.234.56', 'EUR -10,00', '-EUR 10,00 C'])
def test_ambiguous_or_incomplete_lexemes_abstain(make_document, text):
    assert parse_money(text) is None
    scan = scan_money_regions(reconstruct_rows(make_document(text))[0], Tolerances())
    assert scan.incomplete


@pytest.mark.parametrize('currency', ['EUR', 'USD', 'BRL'])
def test_currency_never_selects_decimal_convention(make_document, currency):
    doc = make_document('Período: 01/01/2029 a 31/01/2029\n'
        f'Saldo inicial: {currency} 100.00\nSaldo final: {currency} 105,00\n'
        f'02/01/2029 ALFA +{currency} 10,00\n03/01/2029 BETA -{currency} 5.00')
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    statement = result.interpretation.statement
    assert statement.currency.code == currency
    assert [t.amount for t in statement.transactions] == [Decimal('10'), Decimal('-5')]
    source = result.interpretation.provenance.transactions[0].amount_source
    assert source_tokens(doc, source) == (f'+{currency}', '10,00')


def test_conflicting_currencies_block_before_financial_search(make_document):
    doc = make_document('Período: 01/01/2029 a 31/01/2029\n'
        'Saldo inicial: EUR 100,00\nSaldo final: EUR 110,00\n'
        '02/01/2029 ALFA +USD 10.00')
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.INVALID
    assert result.blocking_capabilities == ('currency_conflict',)
    assert result.interpretation is None


def test_competing_prefixes_cannot_leave_a_currency_inside_description(make_document):
    row = reconstruct_rows(make_document('USD EUR 10,00'))[0]
    assert scan_money_regions(row, Tolerances()).incomplete
    doc = make_document('Período: 01/01/2029 a 31/01/2029\n'
        'Saldo inicial: EUR 100,00\nSaldo final: EUR 110,00\n'
        '02/01/2029 ALFA USD +EUR 10,00')
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS
