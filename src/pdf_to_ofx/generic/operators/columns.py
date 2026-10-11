"""Explicit edge-aligned debit/credit cells, independent of institution or totals."""
from dataclasses import dataclass
import re

from pdf_to_ofx.generic.operators.candidates import OperatorFailure
from pdf_to_ofx.generic.semantics import MoneyRegion
from pdf_to_ofx.generic.structure import Row, Tolerances


CAPTIONS = {
    'débito': 'debit', 'débitos': 'debit', 'debito': 'debit', 'debit': 'debit',
    'crédito': 'credit', 'créditos': 'credit', 'credito': 'credit', 'credit': 'credit',
    'saldo': 'balance', 'balance': 'balance', 'solde': 'balance',
    'deposit': 'credit', 'deposits': 'credit', 'credits': 'credit',
    'withdrawal': 'debit', 'withdrawals': 'debit', 'debits': 'debit',
}


@dataclass(frozen=True, slots=True)
class ColumnHeader:
    row: Row
    roles: tuple[str, ...]
    # Token intervals of compound captions; legacy captions keep one token.
    cells: tuple[tuple[int, int], ...] = ()

    @property
    def signed_table(self) -> bool:
        return self.roles == ('movement', 'balance')

    def bind(self, amounts: tuple[MoneyRegion, ...], tolerances: Tolerances, *, totals: bool = False,
             balance_only: bool = False) -> tuple[str, ...]:
        roles = []
        for amount in amounts:
            owners = []
            cells = self.cells or tuple((i, i + 1) for i in range(2, len(self.row.words)))
            for (index, end), role in zip(cells, self.roles, strict=True):
                words = self.row.words
                left = (words[index - 1].x0 + words[index].x0) / 2
                right = (words[index].x0 + words[end].x0) / 2 if end < len(words) else None
                left_aligned = (abs(amount.x0 - words[index].x0) <= tolerances.row_y
                                and amount.x0 > left and (right is None or amount.x1 < right))
                # Right-edge alignment is separate evidence. A wide value may
                # not reach the preceding caption/cell or the following column.
                right_aligned = (abs(amount.x1 - words[end - 1].x1) <= tolerances.row_y
                                 and amount.x0 > words[index - 1].x1 + tolerances.row_y
                                 and (end == len(words) or
                                      amount.x1 < words[end].x0 - tolerances.row_y))
                if left_aligned or right_aligned:
                    owners.append(role)
            if len(owners) != 1:
                raise OperatorFailure('column_ownership', 'A monetary cell lacks one aligned declared column.')
            roles.append(owners[0])
        if (len(roles) != len(set(roles)) or
                (roles != ['balance'] if balance_only else set(roles) != set(self.roles) if totals else
                 len([role for role in roles if role in {'debit', 'credit', 'movement'}]) != 1)):
            raise OperatorFailure('column_ownership', 'A movement requires exactly one populated debit or credit cell.')
        return tuple(roles)


def observe_column_header(row: Row, tolerances: Tolerances) -> ColumnHeader | None:
    words = [word.text.casefold().rstrip(':') for word in row.words]
    if (len(words) == 6 and words[0] == 'data' and words[1] in {'lançamentos', 'lançamento', 'histórico', 'descrição'}
            and words[2:] == ['valor', '(r$)', 'saldo', '(r$)']):
        if any(row.words[b].x0 - row.words[a].x1 <= tolerances.row_y for a, b in ((0, 1), (1, 2), (3, 4))):
            raise OperatorFailure('column_ownership', 'Signed financial captions require disjoint cells.')
        return ColumnHeader(row, ('movement', 'balance'), ((2, 4), (4, 6)))
    if words[0] not in {'data', 'date', 'fecha'} or not any(CAPTIONS.get(word) in {"debit", "credit"} for word in words[1:]):
        return None
    if (len(words) not in {4, 5} or words[1] not in {'descrição', 'histórico', 'description', 'descripción'}
            or any(word not in CAPTIONS for word in words[2:])):
        raise OperatorFailure('column_ownership', 'Incomplete or conflicting financial column headers.')
    roles = tuple(CAPTIONS[word] for word in words[2:])
    if (set(roles) not in ({'debit', 'credit'}, {'debit', 'credit', 'balance'})
            or len(roles) != len(set(roles))
            or any(b.x0 - a.x1 <= tolerances.row_y for a, b in zip(row.words, row.words[1:]))):
        raise OperatorFailure('column_ownership', 'Financial column headers are not distinct and complete.')
    return ColumnHeader(row, roles)


def description_reference_indexes(row: Row, header: ColumnHeader | None) -> frozenset[int]:
    """A slash-group identifier needs a declared description cell, not arithmetic.

    The complete token cannot be money. Only this observed reference grammar is
    admitted, inside the caption's spatial cell; a decimal or broken amount is
    never suppressed. Its original token remains in description provenance.
    """
    if header is None or not header.signed_table:
        return frozenset()
    left, right = header.row.words[1].x0, header.row.words[2].x0
    return frozenset(i for i, w in enumerate(row.words) if left <= w.x0 < w.x1 < right
        and re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{2,3}){2}/[0-9]{2,4}(?:-[0-9]{1,2})?', w.text))


def declared_description_references(rows: tuple[Row, ...], tolerances: Tolerances) -> frozenset[tuple[int, int, int]]:
    from pdf_to_ofx.generic.operators.candidates import date_candidates, document_date_order, document_period
    observed_headers = tuple(observe_column_header(row, tolerances) for row in rows)
    if not any(header is not None and header.signed_table for header in observed_headers):
        return frozenset()
    order, period = document_date_order(rows), document_period(rows)
    header = None
    output = set()
    for row, observed in zip(rows, observed_headers, strict=True):
        if observed:
            header = observed
        elif header is not None and header.signed_table:
            dates = date_candidates(row, order=order, period=period)
            if dates and dates[0].start == 0 and abs(row.words[0].x0 - header.row.words[0].x0) <= tolerances.row_y:
                output.update((id(row), i, i + 1) for i in description_reference_indexes(row, header))
    return frozenset(output)
