"""Local semantic candidates: dates, declared periods and signed controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import TYPE_CHECKING

from pdf_to_ofx.domain.errors import StatementParseError
from pdf_to_ofx.generic.semantics import (
    ISO_DATE, LONG_DATE, NUMERIC_DATE, SHORT_MONTH_DATE, has_financial_signal, money_regions, parse_date,
)
from pdf_to_ofx.generic.structure import Row, Tolerances

if TYPE_CHECKING:
    from pdf_to_ofx.generic.operators.amounts import MonetaryDiagnostic


class OperatorFailure(StatementParseError):
    def __init__(self, capability: str, reason: str,
                 *, monetary_diagnostics: tuple[MonetaryDiagnostic, ...] = (),
                 stage: str | None = None) -> None:
        self.capability = capability
        self.stage = stage
        self.monetary_diagnostics = monetary_diagnostics
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class DateCandidate:
    value: date
    start: int
    end: int


def date_candidates(row: Row, *, order: str = "day_first") -> tuple[DateCandidate, ...]:
    candidates = []
    for start in range(len(row.words)):
        for count, pattern in ((1, NUMERIC_DATE), (1, ISO_DATE), (5, LONG_DATE), (3, SHORT_MONTH_DATE)):
            end = start + count
            text = " ".join(w.text for w in row.words[start:end])
            if pattern.fullmatch(text):
                value = parse_date(text, order=order)
                if value is None:
                    raise OperatorFailure("date_attribution", "Invalid calendar date in structural region.")
                candidates.append(DateCandidate(value, start, end))
    return tuple(candidates)


def leading_date(row: Row, *, order: str = "day_first") -> tuple[date, int] | None:
    candidate = next((d for d in date_candidates(row, order=order) if d.start == 0), None)
    return (candidate.value, candidate.end) if candidate else None


PERIOD = re.compile(r"per[ií]odo:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})\s+(?:a|até)\s+([0-9]{2}/[0-9]{2}/[0-9]{4})", re.IGNORECASE)


FLOW = re.compile(r"total de (entradas|saídas|créditos|débitos):?", re.IGNORECASE)

WRITTEN_PERIOD = re.compile(
    r"(?:período:\s*)?([0-9]{1,2} de [a-zç]+ de [0-9]{4})\s+(?:a|até)\s+"
    r"([0-9]{1,2} de [a-zç]+ de [0-9]{4})(?:\s+(.*))?", re.IGNORECASE,
)

def _has_date(text: str) -> bool:
    return any(pattern.search(text) for pattern in (NUMERIC_DATE, ISO_DATE, LONG_DATE, SHORT_MONTH_DATE))

def _stamp(row: Row) -> bool:
    return re.match(r"^(?:extrato|documento) gerado (?:em|(?:no )?dia)\b", row.text, re.IGNORECASE) is not None


# New period grammars carry no implicit slash-date convention. Calendar validity
# of their explicit endpoints must prove one order for the entire document.
INTERNATIONAL_PERIOD = re.compile(
    r"(?:statement period|period|période):\s*([0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"\s+(?:to|au)\s+([0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", re.IGNORECASE,
)


def _international_period(match: re.Match) -> tuple[tuple[date, date], str]:
    if bool(ISO_DATE.fullmatch(match[1])) != bool(ISO_DATE.fullmatch(match[2])):
        raise OperatorFailure("date_convention_ambiguous", "Period endpoints use competing date representations.")
    orders = ("day_first",) if ISO_DATE.fullmatch(match[1]) else ("day_first", "month_first")
    possible = []
    for order in orders:
        start, end = parse_date(match[1], order=order), parse_date(match[2], order=order)
        if start is not None and end is not None and start <= end:
            possible.append(((start, end), order))
    if len(possible) != 1:
        raise OperatorFailure("date_convention_ambiguous", "Explicit period does not prove one calendar convention.")
    return possible[0]


def document_date_order(rows: tuple[Row, ...]) -> str:
    orders = set()
    for row in rows:
        match = INTERNATIONAL_PERIOD.fullmatch(row.text)
        if match:
            _, order = _international_period(match)
            if NUMERIC_DATE.fullmatch(match[1]):
                orders.add(order)
        elif PERIOD.fullmatch(row.text) or WRITTEN_PERIOD.fullmatch(row.text):
            # Preserve the historical fixed DD/MM grammar; never reinterpret it.
            orders.add("day_first")
    if len(orders) > 1:
        raise OperatorFailure("date_convention_ambiguous", "Declared calendar conventions conflict.")
    return next(iter(orders), "day_first")


def _period(row: Row) -> tuple[date, date] | None:
    international = INTERNATIONAL_PERIOD.fullmatch(row.text)
    if international:
        return _international_period(international)[0]
    match = PERIOD.fullmatch(row.text) or WRITTEN_PERIOD.fullmatch(row.text)
    if match is None:
        return None
    start, end = parse_date(match[1]), parse_date(match[2])
    caption = match[3] if match.re is WRITTEN_PERIOD else None
    currency_caption = caption is not None and re.fullmatch(r"(?:valores|valor) em R\$", caption, re.IGNORECASE)
    if start is None or end is None or (caption and not currency_caption and
            (has_financial_signal(caption) or _has_date(caption))):
        raise StatementParseError("Invalid or ambiguous declared period.")
    return start, end

def _flow(row: Row, tolerances: Tolerances, *, order: str = "day_first") -> tuple[Decimal, int] | None:
    if _period(row):
        return None
    dated = leading_date(row, order=order)
    offset = dated[1] if dated else 0
    regions = money_regions(row, tolerances)
    if len(regions) != 1:
        return None
    region = regions[0]
    label = " ".join(w.text for w in row.words[offset:region.start])
    match = FLOW.fullmatch(label)
    if match is None:
        return None
    credit = match[1].casefold() in {"entradas", "créditos"}
    source = " ".join(w.text for w in row.words[region.start:region.end])
    if (region.end != len(row.words) or region.money.marker is not None
            or not region.money.explicit_sign or not source.startswith("+" if credit else "-")):
        raise StatementParseError("Flow subtotals require an explicit consistent direction.")
    return region.money.amount, 1 if credit else -1
