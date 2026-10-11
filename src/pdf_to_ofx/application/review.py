"""Session-only source resolution. No extraction, persistence or inference."""
from dataclasses import dataclass

from pdf_to_ofx.application.convert import StatementAnalysis
from pdf_to_ofx.domain.evidence import SourceSpan, TransactionSource
from pdf_to_ofx.generic.structure import Tolerances, reconstruct_rows
from pdf_to_ofx.pdf.provenance import text_lines


@dataclass(frozen=True, slots=True)
class ResolvedSource:
    span: SourceSpan
    tokens: tuple[str, ...] | None


class ReviewSession:
    def __init__(self, analysis: StatementAnalysis) -> None:
        self.sources = {s.transaction_index: s for s in analysis.provenance.transactions}
        self.rows: dict[tuple[str, int, int], tuple[str, ...]] = {}
        document = analysis.document
        if document is None:
            return
        for page, row, text in text_lines(document):
            self.rows["text_line", page, row] = tuple(text.split())
        tolerances = analysis.layout_profile.tolerances if analysis.layout_profile else Tolerances()
        counts: dict[int, int] = {}
        for row in reconstruct_rows(document, tolerances):
            counts[row.page] = counts.get(row.page, 0) + 1
            self.rows["visual_row", row.page, counts[row.page]] = tuple(w.text for w in row.words)

    def transaction_source(self, index: int) -> TransactionSource | None:
        return self.sources.get(index)

    def resolve(self, span: SourceSpan) -> ResolvedSource:
        words = self.rows.get((span.basis, span.page, span.row))
        tokens = words[span.word_start:span.word_end] if words is not None and span.word_end <= len(words) else None
        return ResolvedSource(span, tokens)
