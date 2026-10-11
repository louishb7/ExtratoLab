"""CSV v1: UTF-8, comma, LF, ISO dates, exact signed cents, document order."""
import csv
from decimal import Decimal
from io import StringIO

from pdf_to_ofx.domain.models import Statement
from pdf_to_ofx.validation.statement import validate_statement

HEADERS = ("date", "description", "direction", "amount", "currency", "balance_after")


def protect_text(value: str) -> str:
    # Spreadsheet importers may trim whitespace before recognizing a formula.
    # Prefixing occurs only here; the immutable domain description is untouched.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def money(value: Decimal) -> str:
    return "0.00" if value == 0 else format(value, ".2f")


def generate_csv(statement: Statement) -> str:
    validate_statement(statement)
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADERS)
    for transaction in statement.transactions:
        writer.writerow((transaction.posting_date.isoformat(), protect_text(transaction.description),
                         "credit" if transaction.amount >= 0 else "debit", money(transaction.amount),
                         statement.currency.code if statement.currency else "",
                         money(transaction.balance_after) if transaction.balance_after is not None else ""))
    return output.getvalue()
