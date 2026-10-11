"""Bounded dated wraps and repeated periods preserve original tokens and pages."""
from dataclasses import replace
from decimal import Decimal

import pytest

from pdf_to_ofx.domain.evidence import AnalysisStatus
from pdf_to_ofx.generic.inference import infer_layout
from pdf_to_ofx.pdf.sources import source_tokens
from tests.generic.test_operators import positioned


FRAME = [[(35, 'EXTRATO FICTICIO')], [(35, 'Período: 01/01/2029 a 31/01/2029')]]
BALANCES = [[(35, 'Saldo inicial: R$ 100,00')], [(35, 'Saldo final: R$ 105,00')]]
FIRST = [(35, '02/01/2029'), (140, 'ALFA FICTICIO'), (450, '+R$ 10,00')]
SECOND = [(35, '03/01/2029'), (140, 'BETA FICTICIO'), (450, '-R$ 5,00')]
CONTINUATION = [(140, 'REFERENCIA MULTILINHA')]


def test_wrap_and_page_frame_preserve_each_fragment_and_next_movement():
    doc = positioned(FRAME + BALANCES + [FIRST, CONTINUATION], FRAME + [SECOND])
    for offset in (0, 17):
        shifted = replace(doc, pages=tuple(replace(page, words=tuple(
            replace(word, x0=word.x0+offset, x1=word.x1+offset) for word in page.words)) for page in doc.pages))
        result = infer_layout(shifted)
        assert result.status == AnalysisStatus.SUCCESS
        interpretation = result.interpretation
        assert [t.description for t in interpretation.statement.transactions] == ['ALFA FICTICIO REFERENCIA MULTILINHA', 'BETA FICTICIO']
        assert [t.amount for t in interpretation.statement.transactions] == [Decimal('10'), Decimal('-5')]
        first, second = interpretation.provenance.transactions
        assert len(first.description_sources) == 2
        assert [source_tokens(shifted, source) for source in first.description_sources] == [('ALFA','FICTICIO'), ('REFERENCIA','MULTILINHA')]
        assert first.amount_source.page == 1 and second.amount_source.page == 2
        assert len(interpretation.provenance.monetary_regions) == 4


@pytest.mark.parametrize('continuation', [[(160,'ORPHAN')], [(140,'UNKNOWN R$ 2,00')], [(140,'04/01/2029 ORPHAN')]])
def test_unaligned_financial_or_dated_content_cannot_be_dropped_or_attached(continuation):
    result = infer_layout(positioned(FRAME + BALANCES + [FIRST, continuation], FRAME + [SECOND]))
    assert result.status != AnalysisStatus.SUCCESS
    assert result.interpretation is None


def test_cross_page_continuation_requires_future_explicit_boundary_proof():
    result = infer_layout(positioned(FRAME + BALANCES + [FIRST], FRAME + [CONTINUATION, SECOND]))
    assert result.status != AnalysisStatus.SUCCESS
    assert result.interpretation is None


def test_remote_footer_in_description_column_cannot_borrow_owner():
    doc = positioned(FRAME + BALANCES + [FIRST, CONTINUATION, SECOND])
    page = doc.pages[0]
    shifted = replace(doc, pages=(replace(page, words=tuple(
        replace(word, top=word.top+80, bottom=word.bottom+80) if word.text in {'REFERENCIA','MULTILINHA'} else word
        for word in page.words)),))
    assert infer_layout(shifted).status != AnalysisStatus.SUCCESS


def test_conflicting_repeated_periods_are_not_removed_as_frames():
    other = [[(35,'EXTRATO FICTICIO')], [(35,'Período: 01/02/2029 a 28/02/2029')]]
    assert infer_layout(positioned(FRAME + BALANCES + [FIRST, CONTINUATION], other + [SECOND])).status != AnalysisStatus.SUCCESS


def test_new_continuation_limit_roundtrips_without_changing_legacy_profiles():
    from pdf_to_ofx.generic.profile import LayoutProfile
    result = infer_layout(positioned(FRAME + BALANCES + [FIRST, CONTINUATION], FRAME + [SECOND]))
    assert result.profile.same_page_continuations
    assert LayoutProfile.from_json(result.profile.to_json()) == result.profile
    assert 'same_page_continuations' not in replace(result.profile, same_page_continuations=False).to_json()
