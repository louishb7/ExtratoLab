"""Independent financial expectations; only fixed classifications leave memory."""
import hashlib
import json
from pathlib import Path

from pdf_to_ofx.domain.evidence import AnalysisStatus

CLASSIFICATIONS = frozenset({"correct_approval", "incorrect_approval", "correct_rejection",
                            "false_rejection", "out_of_scope", "unverified"})


def statement_signature(statement):
    def money(value):
        return format(value, ".2f") if value is not None else None
    value = dict(period_start=statement.period_start.isoformat(), period_end=statement.period_end.isoformat(),
                 currency=statement.currency.code if statement.currency else None,
                 opening_balance=money(statement.opening_balance), closing_balance=money(statement.closing_balance),
                 transactions=[dict(date=t.posting_date.isoformat(), description=t.description,
                                    amount=money(t.amount), balance_after=money(t.balance_after)) for t in statement.transactions])
    return signature(value)


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":")).encode("ascii")).hexdigest()


def evaluate(entry, manifest: Path, digest: str, status: str, actual_signature: str | None):
    if not entry.ground_truth_path:
        return "unverified", "truth_missing"
    try:
        # Imported here to preserve the one strict JSON decoder used by Corpus Lab.
        from pdf_to_ofx.corpus.batch import decode_json
        path = Path(entry.ground_truth_path)
        if not path.is_absolute():
            path = manifest.parent / path
        truth = decode_json(path.read_text(encoding="utf-8"))
        allowed = {"schema_version", "sha256", "independently_verified", "evidence_kind", "expectation", "statement"}
        if not isinstance(truth, dict) or truth.keys() - allowed or type(truth.get("schema_version")) is not int or truth["schema_version"] != 1:
            raise ValueError()
        if truth.get("sha256") != digest:
            return "unverified", "truth_hash_mismatch"
        if truth.get("independently_verified") is not True or truth.get("evidence_kind") not in {"synthetic_recipe", "manual_double_review", "official_export"}:
            return "unverified", "truth_not_verified"
        expected = truth.get("expectation")
        if expected not in {"valid_statement", "insufficient_evidence", "out_of_scope"}:
            raise ValueError()
        approved = status == AnalysisStatus.SUCCESS
        if expected == "out_of_scope":
            return "out_of_scope", None
        if expected == "insufficient_evidence":
            if truth.get("statement") is not None:
                raise ValueError()
            return ("incorrect_approval" if approved else "correct_rejection"), None
        validate_expected_statement(truth.get("statement"))
        if not approved:
            return "false_rejection", None
        return ("correct_approval" if actual_signature == signature(truth["statement"]) else "incorrect_approval"), None
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return "unverified", "truth_invalid"


def validate_expected_statement(value):
    from datetime import date
    from decimal import Decimal, InvalidOperation
    if not isinstance(value, dict) or set(value) != {"period_start", "period_end", "currency", "opening_balance", "closing_balance", "transactions"}:
        raise ValueError()
    start, end = date.fromisoformat(value["period_start"]), date.fromisoformat(value["period_end"])
    if start > end or not isinstance(value["transactions"], list) or not value["transactions"]:
        raise ValueError()
    if value["currency"] is not None:
        from pdf_to_ofx.domain.currency import Currency
        Currency(value["currency"])
    def monetary(text):
        if text is not None:
            try:
                valid = isinstance(text, str) and Decimal(text).is_finite() and format(Decimal(text), ".2f") == text
            except InvalidOperation:
                valid = False
            if not valid:
                raise ValueError()
    for field in ("opening_balance", "closing_balance"):
        monetary(value[field])
    for transaction in value["transactions"]:
        if not isinstance(transaction, dict) or set(transaction) != {"date", "description", "amount", "balance_after"}:
            raise ValueError()
        if not start <= date.fromisoformat(transaction["date"]) <= end or not isinstance(transaction["description"], str) or not transaction["description"].strip() or transaction["amount"] is None:
            raise ValueError()
        monetary(transaction["amount"])
        monetary(transaction["balance_after"])
