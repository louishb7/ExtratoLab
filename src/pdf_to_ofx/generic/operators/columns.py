"""Explicit edge-aligned debit/credit cells, independent of institution or totals."""
from dataclasses import dataclass

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

    def bind(self, amounts: tuple[MoneyRegion, ...], tolerances: Tolerances, *, totals: bool = False) -> tuple[str, ...]:
        roles = []
        for amount in amounts:
            owners = []
            for index, role in enumerate(self.roles, 2):
                words = self.row.words
                left = (words[index - 1].x0 + words[index].x0) / 2
                right = (words[index].x0 + words[index + 1].x0) / 2 if index + 1 < len(words) else None
                left_aligned = (abs(amount.x0 - words[index].x0) <= tolerances.row_y
                                and amount.x0 > left and (right is None or amount.x1 < right))
                # Right-edge alignment is separate evidence. A wide value may
                # not reach the preceding caption/cell or the following column.
                right_aligned = (abs(amount.x1 - words[index].x1) <= tolerances.row_y
                                 and amount.x0 > words[index - 1].x1 + tolerances.row_y
                                 and (index + 1 == len(words) or
                                      amount.x1 < words[index + 1].x0 - tolerances.row_y))
                if left_aligned or right_aligned:
                    owners.append(role)
            if len(owners) != 1:
                raise OperatorFailure('column_ownership', 'A monetary cell lacks one aligned declared column.')
            roles.append(owners[0])
        if (len(roles) != len(set(roles)) or
                (set(roles) != set(self.roles) if totals else
                 len([role for role in roles if role in {'debit', 'credit'}]) != 1)):
            raise OperatorFailure('column_ownership', 'A movement requires exactly one populated debit or credit cell.')
        return tuple(roles)


def observe_column_header(row: Row, tolerances: Tolerances) -> ColumnHeader | None:
    words = [word.text.casefold().rstrip(':') for word in row.words]
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
