"""The same approved interpretation gate, independent of OFX identity."""
from pdf_to_ofx.application.convert import ExportReadiness, ExportStatus, StatementAnalysis, _approved_statement
from pdf_to_ofx.domain.errors import ConversionError
from pdf_to_ofx.tabular.csv import generate_csv


def export_csv_analysis(analysis: StatementAnalysis) -> str:
    return generate_csv(_approved_statement(analysis))


def assess_csv_readiness(analysis: StatementAnalysis) -> ExportReadiness:
    try:
        export_csv_analysis(analysis)
    except ConversionError:
        return ExportReadiness(ExportStatus.EXPORT_BLOCKED, ("analysis_not_approved",))
    return ExportReadiness(ExportStatus.READY_TO_EXPORT)
