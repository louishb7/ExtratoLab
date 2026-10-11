"""Portuguese presentation of existing technical outcomes, without raw reasons."""
from decimal import Context, Decimal, localcontext

from pdf_to_ofx.domain.evidence import AnalysisStatus, EvidenceStatus
from pdf_to_ofx.domain.errors import PDFExtractionError

EVIDENCE_LABELS = {
    "opening_closing_reconciled": "Abertura e fechamento",
    "running_balance_verified": "Saldos progressivos",
    "first_movement_verified": "Primeiro movimento",
    "group_subtotals_verified": "Subtotais",
    "credit_total_verified": "Total de créditos",
    "debit_total_verified": "Total de débitos",
    "daily_balances_verified": "Saldos diários",
    "checkpoints_verified": "Pontos de controle",
    "economic_order_verified": "Ordem econômica",
    "financial_coverage_verified": "Cobertura monetária",
}
EVIDENCE_TEXT = {EvidenceStatus.VERIFIED: "Verificado", EvidenceStatus.NOT_AVAILABLE: "Não disponível",
                 EvidenceStatus.NOT_APPLICABLE: "Não aplicável"}
CAPABILITIES = {
    "checkpoint_reconciliation": "Os saldos de controle não correspondem à soma dos lançamentos no intervalo. Confira os saldos e as movimentações do PDF.",
    "financial_reconciliation": "Os saldos e totais declarados não correspondem às movimentações interpretadas.",
    "date_convention_ambiguous": "O período não demonstra uma convenção de datas única e válida.",
    "column_ownership": "Os valores não possuem associação única às colunas de débito, crédito e saldo.",
    "column_direction_conflict": "O sinal de um valor contradiz a coluna de débito ou crédito.",
    "date_attribution": "Uma data não pôde ser associada a um único lançamento com segurança.",
    "date_period": "Há uma movimentação fora do período declarado; ela não será descartada nem redatada.",
    "transaction_segmentation": "As linhas e continuações não puderam ser agrupadas em lançamentos completos com segurança.",
    "financial_coverage": "Existem regiões monetárias sem cobertura completa pela interpretação.",
    "monetary_role_domain_empty": "Não foi possível determinar com evidência suficiente se um valor é movimento, saldo ou controle.",
    "scope_selection": "Não foi possível identificar um único escopo financeiro para as movimentações.",
    "search_budget": "O limite de exploração foi atingido antes de excluir as hipóteses concorrentes.",
    "period_declaration_missing": "O período completo do extrato não foi identificado. Confira se ele está declarado no PDF.",
    "currency_conflict": "Há evidências de moedas contraditórias. Nenhuma conversão de moeda é realizada.",
    "monetary_token_incomplete": "Uma região financeira contém valores sem leitura segura.",
    "financial_caption_ownership": "O cabeçalho monetário não possui uma associação estrutural segura.",
    "summary_value_binding": "Um controle financeiro não pôde ser associado a um único valor.",
    "balance_label_binding": "Os rótulos e valores de saldo não se correspondem com segurança.",
    "summary_adjustment_undetailed": "Há um ajuste financeiro sem movimentações detalhadas correspondentes.",
}
DIRECTIONS = {
    "debit_credit_column": "Cabeçalho da coluna de débito/crédito",
    "direction_marker": "Marcador explícito C/D",
    "signed_group_subtotal": "Sinal do subtotal do grupo",
    "unsigned_credit_convention": "Convenção estrutural de crédito sem sinal",
    "explicit_sign": "Sinal explícito do valor", "signed_amount": "Sinal explícito do valor",
    "credit_debit_marker": "Marcador de crédito/débito", "cd_marker": "Marcador C/D",
    "group_subtotal": "Subtotal do grupo", "subtotal_sign": "Sinal do subtotal",
}


EXPORT_ISSUES = {
    "account_metadata_missing": "São necessários dados bancários adicionais para gerar o OFX.",
    "account_metadata_conflict": "Os dados bancários informados contradizem a conta identificada no PDF. Confira a identidade da conta.",
    "currency_unresolved": "A moeda não foi resolvida pelo documento. Dados bancários não podem fornecer essa evidência.",
    "currency_conflict": "A moeda do perfil contradiz a moeda interpretada. Nenhuma conversão é realizada.",
    "closing_balance_missing": "O saldo final não está disponível. O perfil OFX exige um saldo final declarado; ele não será calculado para preencher essa ausência.",
    "financial_validation_failed": "A validação financeira impede a exportação OFX.",
    "analysis_not_approved": "A interpretação não possui aprovação financeira e proveniência completas para exportação.",
    "export_requirements_invalid": "Os dados bancários não atendem aos requisitos OFX. Confira os identificadores e o tipo de conta.",
    "generation_failed": "Não foi possível gerar o OFX com segurança.",
}


def export_issue_text(issues: tuple[str, ...]) -> str:
    return "\n".join(EXPORT_ISSUES.get(issue, "Um requisito de exportação ainda não foi atendido.")
                     for issue in issues)


def diagnostic_text(analysis):
    if analysis.error_type is PDFExtractionError:
        return ("PDF sem texto extraível. Use um PDF com texto selecionável. "
                "PDFs digitalizados não são suportados; verifique proteção ou danos no arquivo.")
    if analysis.status == AnalysisStatus.SUCCESS:
        lines = ["Interpretação aprovada pelo motor. Verificações disponíveis:"]
        lines.extend(f"{label}: {EVIDENCE_TEXT[getattr(analysis.evidence, key)]}"
                     for key, label in EVIDENCE_LABELS.items())
        return "\n".join(lines)
    lines = [{AnalysisStatus.AMBIGUOUS: "Não foi possível determinar uma interpretação única para este extrato.",
              AnalysisStatus.UNSUPPORTED: "Este formato ainda não é suportado por uma capacidade estrutural segura.",
              AnalysisStatus.INVALID: "Os dados não passaram na validação. Há uma inconsistência financeira ou estrutural."}[analysis.status]]
    if analysis.diagnostic and analysis.diagnostic.value == "material_ambiguity":
        lines.append("Há hipóteses concorrentes compatíveis com as evidências; o motor não escolhe uma delas por preferência.")
    if analysis.budget_exhausted:
        lines.append("O limite de exploração foi atingido. As hipóteses restantes impedem uma aprovação segura.")
    for code in analysis.blocking_capabilities:
        lines.append(CAPABILITIES.get(code, "Uma capacidade estrutural necessária ainda está ausente; o documento requer investigação no Corpus Lab."))
    if analysis.diagnostic and analysis.diagnostic.value == "insufficient_evidence":
        lines.append("Faltam controles independentes ou cobertura completa dos valores monetários.")
    lines.append("Exportação bloqueada. Não edite valores para forçar a aprovação.")
    return "\n".join(dict.fromkeys(lines))


def movement_totals(transactions):
    """Exact display aggregates, independent of the caller's Decimal context."""
    values = [transaction.amount for transaction in transactions]
    if not values:
        return Decimal("0.00"), Decimal("0.00")
    precision = max(value.adjusted() for value in values) - min(value.as_tuple().exponent for value in values) + len(str(len(values))) + 2
    with localcontext(Context(prec=max(28, precision))):
        credits = sum((value for value in values if value > 0), Decimal("0.00"))
        debits = sum((value for value in values if value < 0), Decimal("0.00"))
    return credits, debits
