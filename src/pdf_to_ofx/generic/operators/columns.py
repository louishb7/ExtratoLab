"""Explicit left-aligned debit/credit cells, independent of institution or totals."""
from dataclasses import dataclass

from pdf_to_ofx.generic.operators.candidates import OperatorFailure
from pdf_to_ofx.generic.semantics import MoneyRegion
from pdf_to_ofx.generic.structure import Row, Tolerances


CAPTIONS = {
    'débito': 'debit', 'débitos': 'debit', 'debito': 'debit', 'debit': 'debit',
    'crédito': 'credit', 'créditos': 'credit', 'credito': 'credit', 'credit': 'credit',
    'saldo': 'balance', 'balance': 'balance', 'solde': 'balance',
}


@dataclass(frozen=True, slots=True)
class ColumnHeader:
    row: Row
    roles: tuple[str, ...]

    def bind(self, amounts: tuple[MoneyRegion, ...], tolerances: Tolerances) -> tuple[str, ...]:
        roles = []
        anchors = [word.x0 for word in self.row.words]
        for amount in amounts:
            owners = []
            for index, role in enumerate(self.roles, 2):
                left = (anchors[index - 1] + anchors[index]) / 2
                right = (anchors[index] + anchors[index + 1]) / 2 if index + 1 < len(anchors) else None
                if (abs(amount.x0 - anchors[index]) <= tolerances.row_y and amount.x0 > left
                        and (right is None or amount.x1 < right)):
                    owners.append(role)
            if len(owners) != 1:
                raise OperatorFailure('column_ownership', 'A monetary cell lacks one aligned declared column.')
            roles.append(owners[0])
        if len([role for role in roles if role in {'debit', 'credit'}]) != 1 or len(roles) != len(set(roles)):
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
            or any(b.x0 - a.x1 <= tolerances.token_gap for a, b in zip(row.words, row.words[1:]))):
        raise OperatorFailure('column_ownership', 'Financial column headers are not distinct and complete.')
    return ColumnHeader(row, roles)
