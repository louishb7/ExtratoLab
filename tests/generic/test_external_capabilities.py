"""Fictitious reproductions of external lexical and edge ownership gaps."""
from dataclasses import replace
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.generic.semantics import parse_money, scan_money_regions
from pdf_to_ofx.generic.structure import reconstruct_rows, Tolerances
from pdf_to_ofx.pdf.sources import source_tokens
from tests.generic.test_operators import positioned


@pytest.mark.parametrize('code', ['INR', 'SGD'])
@pytest.mark.parametrize('lexeme', ['1,234.56', '1.234,56'])
def test_explicit_iso_prefix_never_chooses_number_convention(code, lexeme, make_document):
    text = f'-{code} {lexeme}'
    money = parse_money(text)
    assert money.amount == Decimal('-1234.56')
    assert money.currency.code == code
    scan = scan_money_regions(reconstruct_rows(make_document(text))[0], Tolerances())
    assert not scan.incomplete
    assert scan.regions[0].start == 0


@pytest.mark.parametrize('text', ['INR 1,234', 'SGD 1.234', 'INR 1,23.45',
                                 'INR USD 10.00', 'SGD 1 234,56', '-INR 10.00 C'])
def test_new_prefixes_preserve_abstention(text, make_document):
    assert scan_money_regions(reconstruct_rows(make_document(text))[0], Tolerances()).incomplete


def column_document(*, offset=0, wide=False, conflict=False):
    rows = [[(35,'Período: 01/01/2029 a 31/01/2029')],
            [(35,'Saldo inicial: INR 100.00')], [(35,'Saldo final: INR 105.00')],
            [(35,'Date'),(130,'Description'),(340,'Debit'),(450,'Credit'),(570,'Balance')],
            [(35,'02/01/2029'),(130,'FICTITIOUS ALPHA'),(455,'10,00'),(575,'110,00')],
            [(35,'03/01/2029'),(130,'FICTITIOUS BETA'),(345,'5,00'),(575,'105,00')]]
    if wide:
        rows[4][2] = (330,'1.000.010,00')
    if conflict:
        rows[5][2] = (340,'+5,00')
    doc = positioned(rows)
    return replace(doc,pages=tuple(replace(p,words=tuple(replace(w,x0=w.x0+offset,x1=w.x1+offset)
                                                      for w in p.words)) for p in doc.pages))


@pytest.mark.parametrize('offset', [0, 53])
def test_right_edges_prove_columns_and_sign_independently(offset):
    doc = column_document(offset=offset)
    result = infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    assert [t.amount for t in result.interpretation.statement.transactions] == [Decimal('10'),Decimal('-5')]
    assert result.interpretation.statement.currency.code == 'INR'
    for source,label in zip(result.interpretation.provenance.transactions,['Credit','Debit']):
        assert source.direction_basis == 'debit_credit_column'
        assert source_tokens(doc,source.direction_source) == (label,)


@pytest.mark.parametrize('kwargs', [{'wide':True},{'conflict':True}])
def test_crossing_or_contradicting_right_cells_cannot_approve(kwargs):
    assert infer_layout(column_document(**kwargs)).status != AnalysisStatus.SUCCESS


def international_column_document(*, period='May 12, 2029 through June 10, 2029',
                                  dates=('05/13','05/14'), extra=(), total='105.00'):
    return positioned([[(35,period)],[(130,'Opening balance: $100.00')],
                      [(35,'Date'),(130,'Description'),(340,'Debits'),(450,'Credits'),(570,'Balance')],
                      [(35,dates[0]),(130,'FICTITIOUS ALPHA'),(455,'$10.00'),(570,'$110.00')],
                      [(35,dates[1]),(130,'FICTITIOUS BETA'),(345,'$5.00'),(570,'$105.00')],
                      [(130,'Total'),(345,'$5.00'),(455,'$10.00'),(570,'$'+total)],
                      [(35,'Fictitious educational note')],*extra])


def test_declared_dot_table_partial_dates_and_totals_have_complete_ownership():
    doc=international_column_document()
    result=infer_layout(doc)
    assert result.status == AnalysisStatus.SUCCESS
    s=result.interpretation.statement
    assert s.currency is None  # Dollar symbol does not prove USD.
    assert s.closing_balance is None  # Terminal checkpoint does not invent a closing declaration.
    assert [t.amount for t in s.transactions] == [Decimal('10'),Decimal('-5')]
    assert [t.posting_date.isoformat() for t in s.transactions] == ['2029-05-13','2029-05-14']
    evidence=result.interpretation.evidence
    assert evidence.credit_total_verified.value == evidence.debit_total_verified.value == 'verified'
    assert evidence.financial_coverage_verified.value == 'verified'


@pytest.mark.parametrize('kwargs',[
    {'dates':('05/06','05/07'),'period':'May 1, 2029 through July 10, 2029'},
    {'dates':('02/30','05/14')}, {'total':'106.00'},
    {'extra':([(35,'05/15'),(130,'FICTITIOUS HIDDEN'),(455,'$0.00'),(570,'$105.00')],)},
    {'extra':([(35,'Informational fee $1.00')],)},
    {'period':'May 12, 2029 through June 10, 2031'},
])
def test_partial_calendar_contradictory_totals_and_trailing_money_abstain(kwargs):
    assert infer_layout(international_column_document(**kwargs)).status != AnalysisStatus.SUCCESS


def test_new_profile_roundtrip_and_legacy_byte_serialization():
    from pdf_to_ofx.generic.profile import LayoutProfile
    result=infer_layout(international_column_document())
    assert result.profile.decimal_dot_table
    assert LayoutProfile.from_json(result.profile.to_json()) == result.profile
    old=infer_layout(column_document()).profile
    # Explicit caption still admits the same lexical mode; unrelated historical
    # profiles without it must not acquire another field in their serialized JSON.
    assert 'decimal_dot_table' not in replace(old,decimal_dot_table=False).to_json()


@pytest.mark.parametrize('dates', [('5/13','5/14'),('05/13','5/14')])
def test_one_digit_partial_dates_do_not_need_locale(dates):
    assert infer_layout(international_column_document(dates=dates)).status == AnalysisStatus.SUCCESS


def test_dollar_lexemes_without_declared_flow_columns_still_abstain():
    doc=international_column_document()
    page=doc.pages[0]
    # Drop just the caption row, keeping all financial contents unchanged.
    words=tuple(w for w in page.words if w.top!=56)
    assert infer_layout(replace(doc,pages=(replace(page,words=words),))).status != AnalysisStatus.SUCCESS


@pytest.mark.parametrize('amount,approved', [('$10.00', False), ('+$10.00', True)])
def test_manual_table_profile_cannot_replace_direction_evidence(amount, approved):
    from pdf_to_ofx.generic.profile import AmountMode, BalanceMode, DateMode, LayoutProfile
    doc = positioned([[(35, 'Período: 01/01/2029 a 31/01/2029')],
                      [(35, 'Opening balance: $100.00')], [(35, 'Closing balance: $110.00')],
                      [(35, '02/01/2029'), (130, 'FICTITIOUS ALPHA'), (450, amount)]])
    profile = LayoutProfile(DateMode.PER_TRANSACTION, AmountMode.SIGNED, BalanceMode.ABSENT,
                            balance_column=None, decimal_dot_table=True)
    assert (infer_layout(doc, profile=profile).status == AnalysisStatus.SUCCESS) == approved


@pytest.mark.parametrize('code', ['INR', 'SGD'])
@pytest.mark.parametrize('mode', [{}, {'operators': True}, {'legacy': True}])
def test_new_iso_unsigned_magnitude_never_inherits_credit_convention(code, mode):
    doc = positioned([[(35, 'Período: 01/01/2029 a 31/01/2029')],
                      [(35, f'Saldo inicial: {code} 100.00')], [(35, f'Saldo final: {code} 110.00')],
                      [(35, '02/01/2029'), (130, 'FICTITIOUS ALPHA'), (450, f'{code} 10.00')]])
    assert infer_layout(doc, **mode).status != AnalysisStatus.SUCCESS


@pytest.mark.parametrize('code', ['INR', 'SGD'])
def test_new_iso_explicit_signed_direction_still_approves(code):
    doc = positioned([[(35, 'Período: 01/01/2029 a 31/01/2029')],
                      [(35, f'Saldo inicial: {code} 100.00')], [(35, f'Saldo final: {code} 110.00')],
                      [(35, '02/01/2029'), (130, 'FICTITIOUS ALPHA'), (450, f'+{code} 10.00')]])
    assert infer_layout(doc).status == AnalysisStatus.SUCCESS


def test_two_populated_flow_cells_and_currency_conflict_remain_blocked():
    doc=international_column_document()
    from pdf_to_ofx.pdf.document import Word
    p=doc.pages[0]
    extra=Word('$0.00',345,370,74,84,1)
    assert infer_layout(replace(doc,pages=(replace(p,words=(*p.words,extra)),))).status != AnalysisStatus.SUCCESS
    conflicting=positioned([[(35,'May 12, 2029 through June 10, 2029')],
        [(35,'Opening balance: INR 100.00')],[(35,'Closing balance: SGD 110.00')],
        [(35,'05/13/2029'),(130,'FICTITIOUS'),(450,'+INR 10.00')]])
    assert infer_layout(conflicting).status != AnalysisStatus.SUCCESS


def test_actual_pdf_column_extraction_and_exports(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    from pdf_to_ofx.application.convert import analyze_pdf, assess_export_readiness, ExportStatus
    from pdf_to_ofx.application.csv_export import export_csv_analysis
    pdf=tmp_path/'fictitious-right-table.pdf'
    canvas=Canvas(str(pdf),pagesize=(595,842),invariant=1)
    canvas.setFont('Helvetica',9)
    canvas.drawString(35,800,'May 12, 2029 through June 10, 2029 Created on June 10, 2029 at 11:10 AM')
    canvas.drawString(130,770,'Opening balance: $100.00')
    for x,text in [(35,'Date'),(130,'Description')]:canvas.drawString(x,740,text)
    for x,text in [(340,'Debits'),(450,'Credits'),(570,'Balance')]:canvas.drawRightString(x,740,text)
    for y,dt,desc,role,value,bal in [(710,'5/13','ALPHA FICTITIOUS','credit','10.00','110.00'),
                                    (680,'5/14','BETA FICTITIOUS','debit','5.00','105.00')]:
        canvas.drawString(35,y,dt);canvas.drawString(130,y,desc)
        canvas.drawRightString(450 if role=='credit' else 340,y,'$'+value)
        canvas.drawRightString(570,y,'$'+bal)
    canvas.drawString(130,650,'Total')
    for x,text in [(340,'$5.00'),(450,'$10.00'),(570,'$105.00')]:canvas.drawRightString(x,650,text)
    canvas.drawString(35,620,'Entirely fictitious educational note')
    canvas.save()
    analysis=analyze_pdf(pdf)
    assert analysis.status == AnalysisStatus.SUCCESS
    assert analysis.statement.currency is None and analysis.statement.closing_balance is None
    assert '-5.00' in export_csv_analysis(analysis)
    assert assess_export_readiness(analysis).status != ExportStatus.READY_TO_EXPORT
    from pdf_to_ofx.corpus.fingerprint import fingerprint_pdf
    fingerprint=fingerprint_pdf(pdf,analysis)
    assert fingerprint.money_region_count == 8
    assert fingerprint.date_candidate_count >= 2
