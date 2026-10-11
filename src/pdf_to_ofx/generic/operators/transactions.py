"""Candidate transaction boundaries and field regions, before financial roles."""

from dataclasses import dataclass, replace

from pdf_to_ofx.generic.operators.candidates import DateCandidate, OperatorFailure, _flow, _period, date_candidates, document_date_order, document_period
from pdf_to_ofx.generic.operators.columns import ColumnHeader, observe_column_header
from pdf_to_ofx.generic.profile import LayoutProfile
from pdf_to_ofx.generic.semantics import MoneyRegion, balance_labels, has_financial_signal, money_regions
from pdf_to_ofx.generic.structure import Row


@dataclass(frozen=True, slots=True)
class RowCandidate:
    position: int
    row: Row
    dates: tuple[DateCandidate, ...]
    amounts: tuple[MoneyRegion, ...]
    kind: str
    column_header: ColumnHeader | None = None
    column_roles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TransactionSegment:
    position: int
    rows: tuple[RowCandidate, ...]


def semantic_candidates(rows: tuple[Row, ...], profile: LayoutProfile) -> tuple[RowCandidate, ...]:
    output = []
    order = document_date_order(rows)
    period = document_period(rows)
    header = None
    declared_roles = None
    for position, row in enumerate(rows):
        dates = date_candidates(row, order=order, period=period)
        amounts = money_regions(row, profile.tolerances, decimal_dot_table=profile.decimal_dot_table)
        kind = "content"
        observed = observe_column_header(row, profile.tolerances)
        if observed:
            if declared_roles is not None and declared_roles != observed.roles:
                raise OperatorFailure("column_ownership", "Repeated financial column headers conflict.")
            header, declared_roles = observed, observed.roles
            kind = "column_header"
        elif _period(row):
            kind = "period"
        elif (header is not None and header.row.page == row.page and not dates and amounts
              and ' '.join(w.text for w in row.words[:amounts[0].start]).casefold() == 'total'
              and abs(row.words[0].x0 - header.row.words[1].x0) <= profile.tolerances.row_y):
            kind = "column_total"
        elif len(amounts) == 1 and amounts[0].start == 0 and amounts[0].end == len(row.words):
            kind = "monetary_only"
        elif (len(amounts) == 1 and amounts[0].end == len(row.words)
              and " ".join(w.text for w in row.words[:amounts[0].start]).casefold() == "saldo intermediário:"):
            kind = "checkpoint"
        elif _flow(row, profile.tolerances, order=order) is not None:
            kind = "flow"
        elif (len(dates) == 1 and dates[0].start == 0 and
              (dates[0].end == len(row.words) or
               balance_labels(" ".join(w.text for w in row.words[dates[0].end:])) in (("do dia",), ("diário",)))):
            kind = "date_heading"
        elif row.text.casefold().startswith(("opening balance", "closing balance", "beginning balance", "ending balance")):
            kind = "balance_declaration"
        elif row.text.casefold().startswith("saldo ") and balance_labels(row.text) in (
                ("inicial",), ("anterior",), ("final",), ("total",)):
            kind = "balance_declaration"
        roles = ()
        owner = None
        if kind == "column_total":
            roles = header.bind(amounts, profile.tolerances, totals=True)
            owner = header
        if header is not None and kind == "content" and dates and amounts:
            if header.row.page != row.page:
                raise OperatorFailure("column_ownership", "A new page requires its own financial column header.")
            roles = header.bind(amounts, profile.tolerances)
            owner = header
        output.append(RowCandidate(position, row, dates, amounts, kind, owner, roles))
    if declared_roles is not None and any(candidate.kind == "content" and candidate.dates and candidate.amounts
                                          and not candidate.column_roles for candidate in output):
        raise OperatorFailure("column_ownership", "Financial column headers do not cover all dated movement cells.")
    return tuple(output)


def segment_transactions(candidates: tuple[RowCandidate, ...], profile: LayoutProfile) -> tuple[TransactionSegment, ...]:
    segments: list[TransactionSegment] = []
    active = False
    value_left = min((region.x0 for c in candidates for region in c.amounts), default=None)
    previous_page = None
    for candidate in candidates:
        row = candidate.row
        if row.page != previous_page and not profile.carry_date_across_pages:
            active = False
        previous_page = row.page
        if candidate.kind in {"date_heading", "flow", "checkpoint", "column_header", "column_total"}:
            active = False
            continue
        if candidate.kind != "content":
            raise OperatorFailure("transaction_segmentation", "Unexpected declaration inside the transaction scope.")
        if candidate.amounts:
            segments.append(TransactionSegment(candidate.position, (candidate,)))
            active = True
        else:
            if (not active or not segments or has_financial_signal(row.text) or candidate.dates
                    or profile.continuation_left is None or value_left is None
                    or abs(row.words[0].x0 - profile.continuation_left) > profile.tolerances.row_y
                    or row.words[-1].x1 >= value_left):
                raise OperatorFailure("transaction_segmentation", "Unclassified or orphan transaction continuation.")
            segment = segments[-1]
            previous = segment.rows[-1].row
            if profile.same_page_continuations and (
                    previous.page != row.page or row.words[0].top - previous.words[-1].bottom > profile.tolerances.summary_y):
                raise OperatorFailure("transaction_segmentation", "A dated continuation lacks a same-page bounded structural owner.")
            segments[-1] = replace(segment, rows=(*segment.rows, candidate))
    if not segments:
        raise OperatorFailure("transaction_segmentation", "The financial scope contains no transaction segments.")
    return tuple(segments)


def description_intervals(segment: TransactionSegment, date: DateCandidate | None,
                          *, reject_balance_heading: bool = True,
                          ) -> tuple[tuple[Row, int, int], ...]:
    """Description regions exclude date/amount tokens and preserve every line."""
    head = segment.rows[0]
    excluded = {i for region in head.amounts for i in range(region.start, region.end)}
    if date:
        excluded.update(range(date.start, date.end))
    intervals = []
    start = None
    for index in range(len(head.row.words) + 1):
        if index < len(head.row.words) and index not in excluded:
            if start is None:
                start = index
        elif start is not None:
            intervals.append((head.row, start, index))
            start = None
    intervals.extend((candidate.row, 0, len(candidate.row.words)) for candidate in segment.rows[1:])
    text = " ".join(w.text for row, start, end in intervals for w in row.words[start:end])
    if text.casefold().rstrip(":") in {"saldo", "subtotal"}:
        raise OperatorFailure("monetary_role_domain_empty", "A control caption lacks a structural transaction owner.")
    if (not text or has_financial_signal(text)
            or reject_balance_heading and balance_labels(text) and text.casefold().startswith("saldo ")):
        raise OperatorFailure("transaction_segmentation", "Incomplete or unclassified transaction description.")
    return tuple(intervals)
