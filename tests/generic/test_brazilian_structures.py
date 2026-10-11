"""Financial adversaries derived from local document observations, all fictitious."""
from dataclasses import replace
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus, FinancialRole
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.generic.semantics import parse_money, scan_money_regions
from pdf_to_ofx.generic.structure import reconstruct_rows, Tolerances
from pdf_to_ofx.pdf.sources import source_tokens
from tests.generic.test_operators import positioned


@pytest.mark.parametrize('text,expected', [('123,45-', '-123.45'), ('123,45+', '123.45'),
                                         ('R$ 1.234,56-', '-1234.56'), ('123,45 -', '-123.45')])
def test_suffix_sign_is_owned_in_full_and_direction_source(text, expected, make_document):
    money = parse_money(text)
    assert money is not None and money.explicit_sign
    assert money.amount == Decimal(expected)
    scan = scan_money_regions(reconstruct_rows(make_document(text))[0], Tolerances())
    assert not scan.incomplete and len(scan.regions) == 1


@pytest.mark.parametrize('text', ['-123,45-', '+123,45-', '123,45- C', '123,45+ D',
                                 '123,45--', '123,45-+', '123,45−', '123,45(+)'])
def test_competing_or_unobserved_suffix_grammars_abstain(text, make_document):
    assert parse_money(text) is None
    assert scan_money_regions(reconstruct_rows(make_document(text))[0], Tolerances()).incomplete


def table(*, prefix='Extrato de 01/01/2029 até 31/01/2029', bad_control=False,
          reference=False, notes=False, offset=0):
    h = [[(30, prefix)], [(30, 'Saldo inicial: R$ 100,00')], [(30, 'Saldo final: R$ 105,00')],
         [(30, 'Data'), (110, 'Lançamentos'), (400, 'Valor (R$)'), (500, 'Saldo (R$)')]]
    rows = [[(30, '02/01'), (110, 'ALFA FICTICIA' + (' 12.345.67/89' if reference else '')),
             (400, '10,00+'), (500, '110,00')],
            [(30, '03/01'), (110, 'BETA FICTICIA'), (400, '5,00-'), (500, '105,00')]]
    if bad_control: rows[-1][-1] = (500, '106,00')
    if notes: rows += [[(30, 'Observações:')], [(30, 'Nota inteiramente fictícia')]]
    doc = positioned(h + rows)
    return replace(doc, pages=tuple(replace(p, words=tuple(replace(w, x0=w.x0+offset, x1=w.x1+offset)
                                                    for w in p.words)) for p in doc.pages))


@pytest.mark.parametrize('offset', [0, 43])
@pytest.mark.parametrize('reference,notes', [(False, False), (True, True)])
def test_declared_signed_table_partial_dates_and_reference_have_complete_sources(offset, reference, notes):
    doc = table(offset=offset, reference=reference, notes=notes)
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    s = result.interpretation.statement
    assert s.currency.code == 'BRL'
    assert [t.amount for t in s.transactions] == [Decimal('10'), Decimal('-5')]
    assert [t.posting_date.isoformat() for t in s.transactions] == ['2029-01-02', '2029-01-03']
    assert result.interpretation.evidence.financial_coverage_verified.value == 'verified'
    assert len(result.interpretation.provenance.monetary_regions) == 6
    if reference: assert '12.345.67/89' in s.transactions[0].description
    for t, src in zip(s.transactions, result.interpretation.provenance.transactions, strict=True):
        assert parse_money(' '.join(source_tokens(doc, src.direction_source))).amount == t.amount


@pytest.mark.parametrize('prefix', ['Extrato de 31/01/2029 até 01/01/2029',
                                   'Extrato de 01/01/2029 até 31/01/2031',
                                   'Extrato de 01/02/2029 até 28/02/2029'])
def test_bad_or_unbounded_periods_never_supply_a_year(prefix):
    assert infer_layout(table(prefix=prefix)).status != AnalysisStatus.SUCCESS


def test_visualization_period_stamp_is_not_a_third_posting_date():
    doc = table(prefix='período de visualização: 01/01/2029 até 31/01/2029 emitido em: 02/02/2029 12:34:56')
    assert infer_layout(doc).status == AnalysisStatus.SUCCESS


def test_bad_balances_and_hidden_money_in_notes_abstain():
    assert infer_layout(table(bad_control=True)).status == AnalysisStatus.INVALID
    doc = table(notes=True)
    p = doc.pages[0]
    from pdf_to_ofx.pdf.document import Word
    doc = replace(doc, pages=(replace(p, words=(*p.words, Word('1,00', 400, 425, 146, 156, 1))),))
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS


def test_reference_requires_its_declared_description_column():
    doc = table(reference=True)
    p = doc.pages[0]
    doc = replace(doc, pages=(replace(p, words=tuple(w for w in p.words if w.top != 74)),))
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS


def test_daily_controls_in_a_dated_table_do_not_change_later_posting_dates():
    doc = positioned([[(30, 'Extrato de 01/01/2029 até 31/01/2029')],
                      [(30, 'Saldo inicial: R$ 100,00')], [(30, 'Saldo final: R$ 105,00')],
                      [(30, 'Data'), (110, 'Lançamentos'), (400, 'Valor (R$)'), (500, 'Saldo (R$)')],
                      [(30, '02/01'), (110, 'ALFA FICTICIA'), (400, '10,00+')],
                      [(30, '02/01'), (110, 'Saldo do dia'), (500, '110,00')],
                      [(30, '03/01'), (110, 'BETA FICTICIA'), (400, '5,00-')],
                      [(30, '03/01'), (110, 'Saldo do dia'), (500, '105,00')]])
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    assert [t.posting_date.isoformat() for t in result.interpretation.statement.transactions] == ['2029-01-02', '2029-01-03']
    assert sum(a.role == FinancialRole.DAILY_BALANCE for a in result.interpretation.provenance.monetary_regions) == 2


def test_long_deterministic_statement_uses_bounded_search_not_recursive_prefixes(make_document):
    text = ('Período: 01/01/2029 a 31/01/2029\nSaldo inicial: R$ 100,00\nSaldo final: R$ 400,00\n'
            + '\n'.join(f'02/01/2029 OPERACAO FICTICIA {i} +1,00' for i in range(300)))
    result = infer_layout(make_document(text))
    assert result.status == AnalysisStatus.SUCCESS
    assert len(result.interpretation.statement.transactions) == 300
    assert result.explored_hypotheses <= 128 and not result.budget_exhausted


def test_real_pdf_recipe_and_exports(tmp_path):
    from tests.fixtures.brazilian_structures.generate import generate
    from pdf_to_ofx.application.convert import analyze_pdf, assess_export_readiness, ExportStatus
    from pdf_to_ofx.application.csv_export import export_csv_analysis
    from pdf_to_ofx.domain.models import BankAccount
    p = tmp_path / 'fictitious.pdf'; generate(p)
    analysis = analyze_pdf(p)
    assert analysis.status == AnalysisStatus.SUCCESS
    assert len(analysis.statement.transactions) == 3
    assert '1.00' in export_csv_analysis(analysis)
    account = BankAccount('FICTITIOUS', '999', '999', '0001', 'FICT-04')
    ready = assess_export_readiness(analysis, account)
    assert ready.status == ExportStatus.READY_TO_EXPORT
    from pdf_to_ofx.application.convert import export_analysis
    assert '<TRNAMT>1.00' in export_analysis(analysis, account)


@pytest.mark.parametrize('opening', ['31/12 Saldo anterior: R$ 100,00', '01/01 Saldo anterior: R$ 100,00'])
def test_dated_opening_is_a_boundary_not_a_movement(opening):
    doc = positioned([[(30, 'Extrato de 01/01/2029 até 31/01/2029')], [(30, opening)],
                      [(30, 'Saldo final: R$ 110,00')],
                      [(30, '02/01'), (110, 'ALFA FICTICIA'), (400, '10,00+')]])
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    assert result.interpretation.statement.opening_balance == Decimal('100')
    assert len(result.interpretation.statement.transactions) == 1
    assert result.interpretation.provenance.monetary_regions[0].role == FinancialRole.OPENING_BALANCE


@pytest.mark.parametrize('opening', ['30/12 Saldo anterior: R$ 100,00', '03/01 Saldo anterior: R$ 100,00'])
def test_dated_opening_away_from_opening_boundary_abstains(opening):
    doc = positioned([[(30, 'Extrato de 01/01/2029 até 31/01/2029')], [(30, opening)],
                      [(30, 'Saldo final: R$ 110,00')],
                      [(30, '02/01'), (110, 'ALFA FICTICIA'), (400, '10,00+')]])
    assert infer_layout(doc).status != AnalysisStatus.SUCCESS


def test_suffix_does_not_authorize_a_truncated_numeric_prefix(make_document):
    assert scan_money_regions(reconstruct_rows(make_document('1 234,56-'))[0], Tolerances()).incomplete


def test_currency_caption_cannot_override_an_explicit_conflicting_currency():
    doc = table()
    page = doc.pages[0]
    words = tuple(replace(w, text='USD') if w.text == 'R$' else w for w in page.words)
    assert infer_layout(replace(doc, pages=(replace(page, words=words),))).status == AnalysisStatus.INVALID


def test_reference_outside_the_description_cell_is_not_ignored():
    doc = table(reference=True)
    page = doc.pages[0]
    words = tuple(replace(w, x0=460, x1=525) if w.text == '12.345.67/89' else w for w in page.words)
    assert infer_layout(replace(doc, pages=(replace(page, words=words),))).status != AnalysisStatus.SUCCESS


def test_long_deterministic_statement_with_wrong_control_remains_invalid(make_document):
    text = ('Período: 01/01/2029 a 31/01/2029\nSaldo inicial: R$ 100,00\nSaldo final: R$ 401,00\n'
            + '\n'.join(f'02/01/2029 OPERACAO FICTICIA {i} +1,00' for i in range(300)))
    assert infer_layout(make_document(text)).status == AnalysisStatus.INVALID


def test_opening_date_has_only_the_opening_cut_even_in_a_full_civil_year():
    from pdf_to_ofx.generic.operators.candidates import date_candidates, document_date_order, document_period
    doc = positioned([[(30, 'Extrato de 01/01/2029 até 31/12/2029')], [(30, '31/12 Saldo anterior: R$ 100,00')]])
    rows = reconstruct_rows(doc)
    candidate = date_candidates(rows[1], order=document_date_order(rows), period=document_period(rows))[0]
    assert candidate.value.isoformat() == '2028-12-31'


def test_signed_net_total_is_not_reinterpreted_as_a_debit_total():
    doc = table()
    page = doc.pages[0]
    from pdf_to_ofx.pdf.document import Word
    words = tuple(Word(t, x, x+len(t)*5, 128, 138, 1) for x, t in [(110, 'Total'), (400, '5,00'), (500, '105,00')])
    assert infer_layout(replace(doc, pages=(replace(page, words=(*page.words, *words)),))).status != AnalysisStatus.SUCCESS


def test_currency_caption_provenance_resolves_literal_symbols():
    doc = table()
    interpretation = infer_layout(doc).interpretation
    tokens = [source_tokens(doc, src) for src in interpretation.provenance.currency_sources]
    assert ('(R$)',) in tokens


@pytest.mark.parametrize('variant', ['invalid_control', 'hidden_tail', 'omit_period', 'bad_suffix'])
def test_real_pdf_adversaries_block_both_exports(tmp_path, variant):
    from tests.fixtures.brazilian_structures.generate import generate
    from pdf_to_ofx.application.convert import analyze_pdf, export_analysis
    from pdf_to_ofx.application.csv_export import export_csv_analysis
    from pdf_to_ofx.domain.errors import UnsupportedLayoutError, StatementValidationError
    path = tmp_path / 'fictitious.pdf'
    generate(path, **{variant: True})
    analysis = analyze_pdf(path)
    assert analysis.status != AnalysisStatus.SUCCESS
    with pytest.raises((UnsupportedLayoutError, StatementValidationError)):
        export_analysis(analysis)
    with pytest.raises((UnsupportedLayoutError, StatementValidationError)):
        export_csv_analysis(analysis)
