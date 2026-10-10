# Engineering contract

## Product purpose

**ExtratoLab** is a local desktop application and conversion core (Python + PySide6)
for interpreting, reviewing, validating, and exporting PDF bank statements into
deterministic OFX (and future tabular formats) for an accounting office whose
downstream workflow uses Athenas. Processing must remain 100% local and work
offline: financial documents are confidential. Athenas compatibility still
requires a dedicated acceptance test and must not be claimed from synthetic or
unverified examples.

## Product principles

- **Local financial processing:** Process financial document contents locally;
  analysis, validation, and export must never require external servers,
  third-party APIs, or telemetry.
- **Fail-closed financial interpretation:** Prefer deterministic structural
  interpretation and mathematical proof to probabilistic guessing or scoring.
  Fail closed (`AMBIGUOUS`, `UNSUPPORTED`, or `INVALID`) whenever financial data
  is ambiguous, incomplete, or contradictory; never silently discard or invent
  transactions or balances.
- **Structure-based generic engine:** The engine interprets financial structures
  (visual rows, monetary domains, structural operators, bounded hypotheses, and
  independent control intervals), not institution-specific parsers as an
  expansion strategy.
- **Banks are sampling sources:** Banking institutions serve as sampling sources
  for structural diversity in Corpus Lab, never as parser boundaries or routing
  keys for generic interpretation.
- **Evidence-driven evolution:** New capabilities must be guided by concrete
  document diagnostics, structural evidence, and reproducible synthetic
  regression fixtures rather than speculative bank-specific heuristics.
- **Cross-platform support:** Compatibility with both **Linux** and **Windows**
  from a single Python/PySide6 codebase is mandatory.

## Architecture rules

- Keep the analysis, validation, and export core (`pdf/`, `domain/`, `generic/`,
  `validation/`, `ofx/`, `application/`, `corpus/`) independent of the GUI
  (`ui/`). UI code must never contain parsing, hypothesis, or financial
  reconciliation logic.
- Isolate PDF-library calls behind `pdf/extractor.py` and our own immutable
  document model (`ExtractedDocument`, `ExtractedPage`, `Word`).
- Preserve legacy recognized oracles (`SyntheticBankParser`, `InterParser`, and
  legacy M4/M5/M7 paths) for regression verification and FITID stability, while
  expanding coverage exclusively through generic structural operators and
  bounded hypothesis composition.
- Preserve existing FITID generation and financial export semantics; never alter
  FITID algorithms, canonical ordering, or financial behavior without explicit
  justification, migration planning, and regression tests.
- Generate exports from normalized domain models and validate both statement
  invariants and export readiness before publishing. Use `Decimal` for monetary
  values, never binary floating point (`float`).
- Avoid unnecessary persistence; no database without a concrete requirement.
- No OCR until digitally generated PDFs and the desktop review workflow are
  complete and authorized. Avoid premature frameworks or speculative abstractions.
- Keep dependencies minimal and justify additions.

## Privacy and logging rules

- Never commit real client bank statements or upload private financial fixtures.
- `tests/private_fixtures/` and `.corpus/` are local-only and must remain
  ignored by Git.
- Committed fixtures must contain synthetic/fictitious data only.
- Do not persist raw transaction contents in logs or diagnostic reports. Avoid
  printing transaction descriptions, account numbers, or private paths unless
  explicitly requested for local interactive debugging.
- Error messages and batch diagnostics should identify the failure stage and
  blocking capabilities without reproducing confidential document text.

## Testing and portability rules

- Core analysis, diagnosis, Corpus Lab, and export behavior must be testable
  without a graphical display; UI tests must run cleanly under
  `QT_QPA_PLATFORM=offscreen`.
- Specify explicit text encodings (`encoding="utf-8"` or `encoding="ascii"` as
  appropriate) on all text file read/write operations so tests and tools behave
  identically on Linux (UTF-8 default) and Windows (`cp1252` legacy default).
- Guard OS-dependent test setup (such as symbolic link creation on Windows
  environments without Developer Mode or elevated privileges) with conditional
  skips only around the unsupported OS precondition, never masking real
  implementation failures.
- Each supported structural capability must have dedicated synthetic fixtures
  and regression tests covering both success and failure/abstention paths.
  Validation or readiness failures must prevent export.

## Development rules

- Python is the primary language; target Python >= 3.12 and use modern type hints.
- Favor straightforward Python and small domain-oriented functions/classes.
  Prefer the standard library when sufficient and use `pathlib` for paths.
- Never use `float` for money. Keep signed amounts: positive is inflow/credit,
  negative is outflow/debit.
- Do not automatically commit or push changes without explicit user authorization.

## Final task review requirement

Every completed Codex implementation task must end with a review explicitly
answering at least these five concrete questions:

1. What problem was identified or addressed?
2. What was changed to solve it?
3. Why was this approach chosen?
4. What tests or validations were performed? Include commands and outcomes.
5. What risks, limitations, or follow-up work remain?

Every completed task must end with one suggested Git commit message written in
English. Only suggest it; never commit automatically unless explicitly requested.
