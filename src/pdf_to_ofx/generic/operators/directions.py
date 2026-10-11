"""Movement direction is evidence separate from monetary magnitude."""

from dataclasses import dataclass
from decimal import Decimal

from pdf_to_ofx.generic.operators.amounts import AmountRoles
from pdf_to_ofx.generic.operators.candidates import OperatorFailure, _flow
from pdf_to_ofx.generic.operators.transactions import RowCandidate, TransactionSegment
from pdf_to_ofx.generic.profile import AmountMode
from pdf_to_ofx.generic.structure import Tolerances


@dataclass(frozen=True, slots=True)
class DirectionEvidence:
    sign: int
    basis: str
    source_row: RowCandidate
    word_start: int
    word_end: int
    group_position: int | None = None

    def apply(self, magnitude: Decimal) -> Decimal:
        return magnitude if self.sign == 1 else magnitude.copy_negate()


def infer_direction(segment: TransactionSegment, roles: AmountRoles, mode: AmountMode,
                    candidates: tuple[RowCandidate, ...], tolerances: Tolerances,
                    *, carry_across_pages: bool) -> DirectionEvidence:
    head = segment.rows[0]
    if head.column_header is not None:
        index = head.amounts.index(roles.movement)
        role = head.column_roles[index]
        if role not in {"debit", "credit"}:
            raise OperatorFailure("column_ownership", "A balance column cannot supply movement direction.")
        sign = -1 if role == "debit" else 1
        money = roles.movement.money
        if ((money.explicit_sign or money.marker) and (-1 if money.amount.is_signed() else 1) != sign):
            raise OperatorFailure("column_direction_conflict", "Monetary sign contradicts its declared column.")
        header = head.column_header
        word = header.roles.index(role) + 2
        owner = RowCandidate(-1, header.row, (), (), "column_header")
        return DirectionEvidence(sign, "debit_credit_column", owner, word, word + 1)
    if mode != AmountMode.GROUP_SUBTOTAL:
        movement = roles.movement
        money = movement.money
        basis = "direction_marker" if money.marker else "explicit_sign" if money.explicit_sign else "unsigned_credit_convention"
        return DirectionEvidence(-1 if money.amount.is_signed() else 1, basis, segment.rows[0], movement.start, movement.end)
    current: RowCandidate | None = None
    previous_page = None
    for candidate in candidates:
        if candidate.row.page != previous_page and not carry_across_pages:
            current = None
        previous_page = candidate.row.page
        if candidate.kind == "date_heading":
            current = None
        elif candidate.kind == "flow":
            current = candidate
        if candidate.position == segment.position:
            break
    if current is None:
        raise OperatorFailure("direction_inference", "A transaction has no dated direction group.")
    flow = _flow(current.row, tolerances)
    assert flow is not None
    region = current.amounts[0]
    return DirectionEvidence(flow[1], "signed_group_subtotal", current, region.start, region.end, current.position)
