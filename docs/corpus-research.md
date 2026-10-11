# Corpus Lab research protocol — integrated cycles 01 and 02

The existing batch analyzer, deduplication, fingerprints and privacy projection
remain the only corpus infrastructure. Institution metadata never selects an
engine route. Public examples, standards and synthetic fixtures have different
evidentiary strength; none is an automatic claim about all layouts of a bank.

## Admission and privacy

1. Establish permission and usage conditions before adding a document. Record
   provenance, visibility, origin URL where appropriate, retrieval date, country,
   language and financial document class. A public URL is not itself a license.
2. Private originals and truth files stay under ignored `.corpus/` or another
   explicitly authorized local directory. Never commit client PDFs or identifying
   financial contents. Use existing sanitized diagnosis for private benchmarks.
3. Record observed structural features and a conservative structural-family
   identifier. Assign `development` or `evaluation` before implementation.
4. Author independent expectations from a fixture recipe, double manual review or
   an official export. Do not copy an engine SUCCESS into ground truth.
5. Bind expectations to the actual PDF SHA-256. Missing, malformed, unverified or
   mismatched truth never counts as proof. Recheck originals when analyzing.
6. Run analysis and inspect sanitized metrics, failure clusters and any critical
   false approval before changing the engine. Regress the complete corpus after
   each capability change. Keep old reports outside the repository.

V1 manifests remain compatible. V2 requires an explicit dataset and adds:
`authorization`, `usage_conditions`, `observed_features` (a list of strings),
`evidence_kind`, `validation_status`, `structural_family`, `ground_truth_path`.
Other text metadata is local-only and never copied into diagnostic reports.

```json
{"schema_version":2,"corpus_id":"demo-01","local_path":"demo.pdf","source_kind":"synthetic","public_or_private":"public","country":"BR","language":"pt","document_kind":"bank_statement","authorization":"Fictitious recipe","usage_conditions":"Tests only","observed_features":["signed_amount","running_balance"],"evidence_kind":"synthetic_recipe","validation_status":"recipe_reviewed","dataset":"development","structural_family":"signed-running","ground_truth_path":"demo.truth.json"}
```

Ground truth schema 1 uses `schema_version`, exact `sha256`,
`independently_verified: true`, evidence kind (`synthetic_recipe`,
`manual_double_review`, `official_export`) and expectation (`valid_statement`,
`insufficient_evidence`, `out_of_scope`). `valid_statement` also requires a
`statement` object: ISO period dates, explicit currency or null, canonical decimal
opening/closing strings or null, and an ordered list of transactions with `date`,
original `description`, signed `amount`, and nullable `balance_after`. Monetary
strings use two decimal places. The generator contains working examples; it
writes expected financial values from the authored recipe, never from analysis.
For negative/out-of-scope fixtures, omit `statement`. The expectation is a human
assertion with provenance, not a cryptographic guarantee of its correctness.

## Evaluation and regression

Five verified classes are distinguished: correct approval, incorrect approval,
correct rejection for insufficient evidence, rejection of a demonstrably valid
statement, and outside declared scope. A sixth `unverified` class records absent
or unusable truth. Dates, currency, descriptions, signed values, available balances
and document order are compared exactly through an in-memory canonical digest.
Account metadata and bank/layout namespaces are not the financial truth.
No financial snapshot or digest is written to sanitized reports.

Correct coverage = correct approvals / (correct approvals + false rejections).
Approval precision = correct approvals / (correct approvals + incorrect approvals).
A zero denominator gives null. Neither metric covers unverified documents or
claims global precision. Report both denominators and fixture provenance.
Incorrect approval is critical. Corpus report CLI returns nonzero for critical
false approvals, truth errors, input/report errors or detected split leakage.
Rejected financial interpretations are normal research outcomes.

Metrics are also reported separately for development and evaluation; documents
with exact duplicates or a declared structural family present in both sets are
excluded from these per-set denominators. `excluded_split_leak_documents` records
the unique excluded documents per set. Whole-corpus counts still describe all
unique documents; they do not represent independent held-out performance when
leakage exists. A malformed metadata type is recorded as a row error and does
not stop the remaining batch.
Exact hashes and declared family hashes are checked across both sets before
aggregation of duplicates. Repeated documents never inflate metric denominators.
Conflicting verified expectations for the same bytes are unverified and reported;
an incorrect approval among conflicting expectations still triggers the critical
counter. Family IDs require conservative human review: they do not automatically
detect all near-duplicate PDF structures. Separate IDs alone do not prove
structural independence. These twelve authored cases are reserved partitions for
regression, not an externally blinded evaluation study.

Compare sanitized reports over shared SHA-256 documents using:

```bash
pdf-to-ofx corpus report /local/current.jsonl --baseline /local/baseline.jsonl --json
```

The comparison identifies added/shared documents, gained/lost correct approvals,
new false approvals and newly observed failure clusters. A gain can be attributed
to a capability only in controlled runs with identical documents and unchanged
independent expectations. New sample populations cannot prove an engine gain.
The current structural signature includes verdict observations; it is not a
perfect duplicate-layout detector. Diversity is the count of human-declared
families plus the existing observed/candidate/verified capability matrix.

## Concept taxonomy

| Research category | Existing concepts and structural questions |
| --- | --- |
| Identity and scope | BankAccount (export only), DocumentRegion, financial_scope; one account/scope versus snapshots or limits |
| Time | Statement period, posting dates, Chronology, date SourceSpan; booking versus value date and outside-period movements |
| Movements | Transaction, amount modes, direction basis; signed values, C/D and separate debit/credit columns |
| Balances | Boundary balances, balance_after, BalanceCheckpoint; booked versus available balance and sparse controls |
| Financial controls | EvidenceReport, subtotals, declared totals, control intervals; independent arithmetic and complete ownership |
| Visual/language structure | ExtractedDocument/Word, Row, LayoutProfile/Tolerances; frames, wrapped descriptions, pagination, lexical conventions |
| Integrity and evidence | Provenance, TransactionSource, monetary assignments, financial coverage and search limits |

The taxonomy maps onto existing domain objects; no duplicate domain class or
institution-specific parser was introduced.

## Sources consulted and rechecked on 2026-10-10

- [ISO 20022 cash management MDR, maintenance 2018–2019](https://www.iso20022.org/sites/default/files/documents/messages/mdr_part_2/ISO20022_MDRPart2_BankToCustomerCashManagement_2018_2019_v1_0.pdf):
  camt.053 models account statements, entries, currency and credit/debit indicators.
  This is message semantics, not a mandatory visual PDF layout. We did not claim
  conformance or implement XML ingestion.
- [Open Banking UK transaction resource v3.1.9](https://openbankinguk.github.io/read-write-api-site3/v3.1.9/resources-and-data-models/aisp/Transactions.html):
  amount/currency, credit/debit, booking/value dates, transaction status and typed
  balances are distinct concepts. Pending movements can be mutable. The version
  consulted is a historical public specification, not a claim about the latest API.
- [Open Banking Brasil public developer documentation, historical rc6.2](https://openbanking-brasil.github.io/areadesenvolvedor/versions/v1.0.0-rc6.2/index.html):
  transactions distinguish credit/debit indicators, currency and dates. An Open
  Finance Atlassian page was inaccessible in the tool, so we used this official
  historical documentation and did not assert current normative requirements.
- [ASC X9 BTRS overview](https://x9.org/standards/btrs/) and
  [format-guide/code-list access page](https://x9.org/standards/btrs/download-btrs/):
  separate balance, summary and transaction reporting concepts motivate controls
  and reconciliation experiments. The overview was consulted; full licensed format
  conformance was not tested or claimed.

These sources inform conceptual experiments. The EN/ES/FR visual recipes and
localized captions are author-created hypotheses; they are not quoted bank
examples or layouts mandated by the standards. No public bank statement PDF was
collected and no financial document was uploaded.

## Reproduce the international population (historical baseline below)

```bash
python tests/fixtures/international/generate.py /local/new-empty-directory
pdf-to-ofx corpus analyze /local/new-empty-directory/corpus.jsonl -o /local/run.jsonl
pdf-to-ofx corpus report /local/run.jsonl --json
python -m pytest tests/corpus -q
```

PowerShell uses the same Python/CLI commands with Windows paths. Generation
refuses a nonempty directory and uses invariant ReportLab bytes. All committed
recipes and expectations are fictitious. There are 8 development and 4 evaluation
cases, 12 unique declared structural families, and no duplicate documents.

| Case | Engine outcome | Independent evaluation | Primary limitation |
| --- | --- | --- | --- |
| signed-running | SUCCESS | correct approval | signed values and running balances |
| cd-markers | SUCCESS | correct approval | explicit C/D with boundary balances |
| english-us-number | UNSUPPORTED | false rejection | date attribution / month-first range |
| spanish-euro | UNSUPPORTED | false rejection | monetary inventory / EUR lexical evidence |
| french-iso-dates | UNSUPPORTED | false rejection | monetary inventory; ISO dates and labels also require later investigation |
| separate-debit-credit-columns | INVALID | false rejection | column ownership/direction not proved; checkpoint contradiction |
| wrapped-repeated-page | UNSUPPORTED | false rejection | transaction segmentation across wrap/frame/page composition |
| unsigned-flow-subtotals | SUCCESS | correct approval | explicit signed owners, declared totals |
| outside-period | INVALID | correct rejection | date outside declared period |
| pending-separate-control | UNSUPPORTED | correct rejection | no supported booked/pending scope composition |
| missing-period | UNSUPPORTED | correct rejection | explicit period absent |
| conflicting-summary | INVALID | correct rejection | arithmetic contradiction |

Baseline: 3 correct approvals, 5 false rejections, 4 correct rejections,
0 incorrect approvals and no unverified expectations. Correct coverage is 3/8
(37.5%), approval precision is 3/3 (100%) **only within this small synthetic set**.
The old Corpus Lab demo remains four unique documents with one outcome of each
status, one duplicate and one intentional missing file; it has no independent
truth and therefore cannot contribute to precision or correct-coverage metrics.

At the end of cycle 01 no optional engine capability was changed: the language/date/column/page gaps
require further controlled structural investigation. No claim about new real
bank coverage, native Windows execution or Athenas acceptance follows from these
numbers. Next work should isolate numeric/currency lexical conventions from
language, prove debit/credit-column ownership, and model temporal/booked scopes
with positive and abstention fixtures before broadening approval.

## Cycle 02 controlled comparison

The original `cases.json`, rendered PDF bytes and financial ground truth remain
unchanged. The table above preserves the cycle 01 baseline. Sequential runs over
the same SHA-256 population establish these gains:

| Run | Correct approvals | False rejections | Correct rejections | Incorrect approvals | Gain |
| --- | ---: | ---: | ---: | ---: | --- |
| New checkout baseline | 3 | 5 | 4 | 0 | none |
| Exact ISO-prefixed monetary lexemes | 4 | 4 | 4 | 0 | spanish-euro |
| Calendar evidence, ISO dates and named controls | 6 | 2 | 4 | 0 | english-us-number, french-iso-dates |
| Explicit debit/credit cell ownership | 7 | 1 | 4 | 0 | separate-debit-credit-columns |
| Bounded dated wrap and repeated period frame | 8 | 0 | 4 | 0 | wrapped-repeated-page |

No gains/losses are attributed to new documents. Original development coverage
is 6/6 and reserved evaluation coverage is 2/2. Both sets have been inspected
during development and neither is an externally blinded test. Approval precision
of 8/8 describes only this synthetic population. Real institution coverage and
Athenas acceptance remain unverified.

`adversarial.json` adds nine separate development recipes: ambiguous monetary
precision, conflicting currency prefixes, competing slash calendars, duplicate
column captions, two populated flow columns, a monetary continuation neighbor,
unproved cross-page continuation, incompatible controls and an out-of-period ISO
movement. All have independently authored negative expectations and are rejected;
they do not contribute to the original valid-document denominator. Generate with
`generate.py OUTPUT --cases tests/fixtures/international/adversarial.json`, then
use the same analyzer/report commands. No parallel corpus infrastructure exists.

Corpus privacy now recognizes the fixed technical codes `column_ownership`,
`column_direction_conflict` and `date_convention_ambiguous`; arbitrary unknown
labels remain hashed. Date observations use the same declared calendar evidence
as the engine without choosing a financial interpretation. New failure clusters
are visible while raw content remains excluded.

At the end of cycle 02, limits included unsupported monetary affixes, unspecified
precision, right-aligned debit/credit cells, more than one occupied flow column, missing
page captions, booking/value-date ownership, booked/pending scope composition
and new automatic cross-page description attachment. Independent controls, exact
coverage, bounded search and export readiness still gate every approval/export.


## Cycle 03 external development comparison

Use the existing analyzer and evaluation schemas; never upload financial contents
or treat another parser output as truth. The 55-PDF local collection remains
ignored and its original bytes/hashes are unchanged. Preserve the original V1
baseline; adding later independent expectations belongs in a separate evaluated
copy, not an overwritten baseline.

| Measure | Before | After | Denominator/limitation |
| --- | ---: | ---: | --- |
| Documents / input errors | 55 / 0 | 55 / 0 | same 55 unique SHA-256 documents |
| SUCCESS / UNSUPPORTED | 0 / 55 | 2 / 53 | status alone does not prove correctness |
| Correct approvals | 0 | 2 | two reviewed valid expectations |
| Incorrect approvals | 0 | 0 | no unverified successes; rejection correctness mostly unknown |
| False rejections | 2 | 0 | retrospectively evaluated on the same two frozen expectations |
| Observed valid coverage | 0/2 | 2/2 | development subset, not all external documents |

Final conservative scope: A=2 reviewed valid/elegible, B=12 financially incomplete
structural examples, C=3 other financial categories, D=2 mixed demonstrations,
E=0 without extractable text, F=36 needing human classification/reference review.
C+D=5 are outside the declared bank-statement denominator. Complete semantic
classification of all documents is not established.

Two caption/layout variants from SyntheticBank gained support through generic
right-edge ownership, exact table decimal magnitudes, English named periods,
unique short-date calendar occurrences and verified terminal totals. They are
variants of one external collection, not three independent source families.
Expected finances were prepared separately using inspected generator semantics,
Poppler bbox and layout projections, complete movement/balance/total checks, then
compared through the existing financial signature evaluator. The random source
ledger is unavailable; preparation occurred during development, not a blind
acceptance test, and no second human audit was performed. Truth and original PDFs
stay local and are excluded from deliverables.

Final first blockers are 36 monetary_token_incomplete, eight column_ownership,
eight date_attribution and one visual_structure. Improved first stages expose
later blockers without implying financial validity. Sectioned flow tables,
compound headers, unsupported affixes/precision, dual dates, multiple scopes,
monetary summaries and watermark-damaged geometry require further evidence-driven
work. The 12 NoUpload generator examples print absolute amounts without direction;
do not reconstruct signs from balancing arithmetic alone.

The optional `decimal_dot_table` profile field is a lexical convention, not a
currency/direction assertion. False remains omitted from historical JSON output.
Automatic inference admits it only after observing complete flow columns;
manual profiles still require a signed/marked/group/column direction owner.
New INR/SGD magnitudes carry the same requirement outside table mode, including
legacy/oracle entry points; a new currency cannot inherit an implicit credit sign.
Dollar-symbol currency stays unknown. Total balance is a checkpoint, never an
invented closing balance. Thus these new approvals are CSV-ready, not OFX-ready.

Linux/Python 3.12 regression and offscreen UI were exercised. Native Windows,
Python 3.13, actual FAT/exFAT/network-share publication and Athenas remain
acceptance work. An existing CI matrix is an execution recipe, not execution
proof. No external PDF or truth is committed, and no new collection-specific
parser or evaluation subsystem was created.

## Cycle 04: Brazilian documentary research and bounded operators

The ignored local catalog is `.corpus/pesquisa-br-01/`. The authorized user
collection contains 28 PDFs / 26 unique hashes; directory membership does not
prove Brazilian origin or statement validity. Eight unique documents were
preliminary digital statement candidates, including two English examples. Six
Portuguese/BRL candidates belong to five structural families. Other materials
include three compilations, twelve visual PDF wrappers, a blank model, an
educational guide and an advertorial reference. These do not belong in the
verified financial denominator.

The [Alterdata layout section](https://ajuda.alterdata.com.br/packupbase/tema-eescriture/eescriture-layouts-reconhecidos-pelo-eescriture)
exposed 47 unique institution pages, 255 named variant labels and 256 images
(238 PNG / 18 JPEG), with zero available PDFs, exact duplicate downloads or
failed requests. Original bytes, source URLs and SHA-256 stay local. Usage rights
and personal-data review remain undetermined: every image is quarantined and
none was used as a digital financial acceptance case or redistributed. Public
access is not a redistribution license. No OCR was introduced.

The original full-collection baseline remains immutable: one SUCCESS and 25
UNSUPPORTED, including one extraction failure. Five of seven preliminary
candidate families were assigned to development and two to reserved evaluation
before financial changes. After separating the English examples, the domestic
subset has three development and two evaluation families; its 60/40 split is
reported rather than relabeled to claim 70/30. No reserved financial answers
were used for tuning, and exact/family split leakage remained zero.

New generic operators recognize one trailing ASCII monetary sign, the explicit
Portuguese `Extrato de ... até ...` / visualization-period declarations,
compound `Valor (R$)` / `Saldo (R$)` captions with exclusive aligned ownership,
description-cell slash-group identifiers, a dated opening balance at exactly the
opening cut, and dated daily controls without turning them into date groups.
An explicit `Observações` boundary accepts only a financially empty tail.
Long singleton suffixes (at least 64 transactions) propagate once through the
same constraints and ledger instead of consuming one recursive search state per
transaction. The 4-local / 128-global budgets still constrain alternatives;
ambiguous, contradictory or unowned financial contents still block export.
Historical FITID algorithms and export semantics were not changed.

Corpus Lab now accepts `independent_document_reconstruction` as an evaluation
reference kind. This describes expected fields reconstructed with an independent
PDF extractor, documentary controls and a pinned source hash, **before comparison
with the engine**. It is not another parser's result, a bank ledger or a second
human audit. Full expected financial values remain in ignored local truth files;
reports contain only classifications, hashes and structural counts. This extends
research evaluation, not financial acceptance or export policy.

A Poppler reconstruction of the already-approved document independently matches
all 13 movements, descriptions, dates, eleven directional subtotals and boundary
balances. Replaying HEAD `9fc7b64` confirms it was already a correct approval.
A second document agrees between Poppler and positioned-word extraction on 145
movements and 21 daily controls, but ten movements lie outside its declared
period and 19 of 20 consecutive control intervals do not reconcile. It remains
rejected. These two documentary references are not blind bank acceptance tests.

Final results remain one correct approval and 25 unsupported documents in the
local collection: **zero new independently verified external financial gains**.
Adding a reference to an old SUCCESS is a verification gain, not an interpreter
coverage gain. Compare final results with the separately annotated baseline
replay, while preserving the original unverified baseline. The historical 55
international PDFs retain two correct approvals and 53 unsupported outcomes;
all original hashes and expectations are unchanged.

Open blockers include secondary financial snapshots/investment/limit regions,
nonstandard periods and partial dates, unowned signs, offset rows, spaced glyphs,
compound flow captions and multiple temporal scopes. Valid fully reviewed
Brazilian acceptance documents are still needed. Native Windows, Python 3.13,
FAT/exFAT/network-share publication and Athenas import remain unverified. Passing
synthetic fixtures does not establish support for the depicted institutions.
