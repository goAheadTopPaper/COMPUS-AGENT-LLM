# PolyU academic policy and faculty retrieval: Part 1

Local evidence retrieval module for the COMP5584 group project. This repository
does not implement the group's Planner, Answerer, Verifier, Schedule Agent or UI.

## Part 1 testing and retrieval improvements

Run `python -X utf8 scripts/check_part1_acceptance.py` to reproduce the 20-question
passage-level development evaluation and full local source/index integrity check.
See `data/part1_test_report.md` for measured before/after results and supporting
passage ranks. The original before snapshot is preserved. These are development
cases used for fixes, not an independent benchmark or final-answer accuracy.

Recent fixes cover deferment paraphrases, illness-related missed assessments,
unpaid-fee consequences, subject-result appeals, credit-transfer applications,
UHS abbreviation routing and counselling appointment instructions. JS programme
IDs no longer enter the subject-code filter. Multi-part programme questions keep
evidence from each requested field. Handbook appendix/chapter labels no longer
inherit numbered body sentences. Conflicting entry-year/term filters raise
ValueError, just as conflicting academic-year filters do.

The response adds `query_expansions` and `preferred_policy_sections` to expose
retrieval hints. Existing evidence IDs, citations and integration methods remain
available; agents can still pass explicit scope filters and request context.

## School-wide expansion — 20 November 2026

The saved current official catalogues now cover **409 programme detail pages**:
245 undergraduate pages across five admission pathways, 129 September 2027 taught
postgraduate pages, and 35 January 2027 taught postgraduate pages. Pages are not
unique degrees: pathways and specialisms can share a programme code.
The Graduate School research directory and 28 linked research-information pages
are included, plus 229 student-service sources across the whole active collection.
Research-detail and empty service-page failures are logged.

For exhaustive listings use `policy_rag.directory.list_programmes()` or:

```powershell
python -X utf8 -m policy_rag.directory --student-type undergraduate --admission-pathway jupas --output data/all_jupas_programmes.json
python -X utf8 -m policy_rag.directory --student-type taught_postgraduate --entry-term January --output data/all_january_programmes.json
```

Do not present the top five retrieved passages as a complete university list.
The directory returns all matching catalogue records with official source URLs.
Service queries naming a page prefer that service's own evidence. UHS eligibility
queries prefer passages stating student eligibility over general health-topic
indexes. `preferred_service_evidence` reports this heuristic. A clinic-specific
passage still requires scope review and must not establish every service's policy.
Research programmes are listed by academic unit in the saved Graduate School
directory, rather than included in the taught/undergraduate structured listing.

New search parameters: `entry_term` (January/September) and `admission_pathway`
(jupas/non-jupas/non-jupas-adhd-grad/international/jee). Their CLI forms are
`--entry-term` and `--admission-pathway`. JS programme IDs are supported.
Responses flag missing term/pathway clarification when multiple versions match.
January 2027 corresponds to 2026/27; September 2027 corresponds to 2027/28.
Current admissions coverage does not establish requirements for September 2026
admission cohorts. Full PRDs for every programme/cohort remain outside coverage.
See `files/schoolwide/COLLECTION_README.md` and `data/schoolwide_coverage.json`.

## Ready-to-use data

- 969 indexed sources, including 11 locally derived dated faculty catalogues.
- 12,254 cited passages, covering the existing regulations and public information
  from 39 academic units plus the university academic-unit directory.
- Three low-text pages are excluded pending visual review. Faculty pages are
  snapshots, not complete departmental websites or cohort-specific PRDs.
- Annual policy handbooks: 2024/25, 2025/26, 2026/27.
- Added 13 public PRDs labelled 2026/27, 75 Computing subject forms, four programme
  guidance pages and 12 service sources. See files/extended_resources/COLLECTION_README.md.
- Detailed programme-entry pages: 129 pages for September 2027 entry (2027/28).
- Explicit academic/entry-year filters exclude undated and different-year evidence.
  No-year policy questions retain a 2026/27 default; academic-information questions
  have no implicit year. Programme questions without a year flag that clarification is needed.
- SQLite stores passage metadata, BM25 statistics, TF-IDF vectors and MiniLM vectors.
- Long documents use normalized mean pooling of overlapping encoder token windows.
- Faculty HTML cleaning excludes browser/search/cookie UI and embedded news blocks.
- Handbook pages split at labelled subsections, with distinct subject-withdrawal
  and programme-withdrawal topics. Scope-specific queries prioritise the matching
  topic; comparisons keep both and ambiguous withdrawal questions flag clarification.
- Programme detail pages use only their main article. Related-programme cards,
  promotional events and general admissions navigation are excluded. Summary,
  curriculum, credits, fees and admissions fields have distinct section citations.
  Credit/fee/duration questions prioritise the appropriate sections.
- Programme names stay with their codes. Short programme lists remain whole;
  longer lists split at entry boundaries (up to about 800 words per group).
- Academic programme/contact/overview requests prefer the corresponding page type
  if matching candidates exist. A response can contain fewer than top_k results
  instead of adding unrelated page categories. This is a transparent rule heuristic,
  not a learned reranker or a guarantee of answer correctness.

## Setup and queries

```powershell
python -m pip install -r requirements-semantic.txt
python -X utf8 -m policy_rag.retrieve --query "Can I withdraw from a subject after the deadline?" --method hybrid --domain policy
python -X utf8 -m policy_rag.retrieve --query "What taught postgraduate programmes does FCMS offer?" --method hybrid --domain academic_information --unit "Faculty of Computer and Mathematical Sciences"
```

The model weights are NOT in the ZIP; first use needs internet to populate the
local model cache. Once cached, add --offline to avoid network checks. No API key
is needed. Searching with --method bm25 or --method vector needs only standard
Python and uses lexical ranking; semantic/hybrid requires sentence-transformers.

For file output, add `--output data/my_query.json`. Do not pipe Unicode JSON
through Windows PowerShell 5.1; direct saving prevents text corruption.

## Integration contract

```python
from policy_rag.retrieve import PolicyRetriever

retriever = PolicyRetriever()  # reuse the object across queries
response = retriever.search(
    "What taught postgraduate programmes does FCMS offer?",
    method="hybrid",
    knowledge_domain="academic_information",
    unit="Faculty of Computer and Mathematical Sciences",
    entry_year=2027,
    top_k=5,
)
```

Each result contains evidence_id, source_id, quoted text, citation (title, URL,
page/section), source_type, knowledge_domain, faculty, unit, page_type, captured_at,
score and warnings. Scores measure relevance, not factual confidence.
Programme-list results additionally report programme_codes and complete_source_text
(meaning all cleaned text of that source is in one passage, not all university offerings).
preferred_page_type and page_type_preference_applied describe the ranking heuristic.
Programme-detail results additionally expose programme_section and complete_section_text.
complete_source_text is false for a section excerpt even if that section fits in
one passage. Preferred sections are reported in preferred_programme_sections.

The Planner should set knowledge_domain explicitly: policy, academic_information,
student_services or all. Default auto routing is a small keyword heuristic, not an intelligent
classification guarantee. General withdrawal/credit/examination questions select
policy; faculty/programme/contact questions select academic_information.
Filtering a specific unit uses its complete official name, case insensitive.

Preserved parameters: student_type, academic_year, programme_code,
admission_cohort, source_type, subject_codes, top_k. New parameters: entry_year and
strict_year. `context(evidence_id)` returns
adjacent passages from the same source. Programme metadata is incomplete: do
not infer programme-specific eligibility or graduation requirements.

## Rebuild and test

```powershell
python scripts/rebuild_project.py
```

Reuses local downloaded files and a cached model by default. Add --online to
allow downloading a missing model. It rebuilds catalogues, extraction and vectors,
runs policy and faculty integration checks, then recreates the handoff ZIP.
It does not crawl websites. Download collection is a separate explicit action.

Policy checks: scripts/check_part1.py. Faculty checks:
scripts/check_faculty_integration.py. Reports are saved under data/. These are
development checks, not an independent benchmark or generated-answer evaluation.
Old test_q1.json through test_q10.json record the earlier policy-only index and
are retained as historical records, not relabelled as new-index results.

## Files and limitations

- files/School Regulation/: original rules and registration documents.
- files/faculty wise rules/: public HTML snapshots and download provenance.
- data/: source catalogue, clean records, passages, index, reports and saved tests.
- policy_rag/: extraction and retrieval implementation.
- output/part1_handoff.zip: current teammate handoff.
- output/part1_before_faculty_update.zip: previous release backup, when available.

No live vacancies or authenticated student records are included. PRD coverage is
partial; every programme and cohort is not covered. Faculty pages may mix entry years.
Mixed policy pages require clause-level eligibility checks. Screenshot-only PDF
content has not been OCRed. Related retrieval results do not prove answerability;
the group's Answerer and Verifier must handle absent evidence and source conflicts.

## Year-specific and programme-specific queries

```powershell
python -X utf8 -m policy_rag.retrieve --query "What are the subject withdrawal rules?" --domain policy --academic-year 2025/26 --method hybrid --offline
python -X utf8 -m policy_rag.retrieve --query "How many credits are required for Metaverse Technology?" --domain academic_information --programme-code 61038 --entry-year 2027 --method hybrid --offline
python -X utf8 -m policy_rag.retrieve --query "What programmes does FCMS offer?" --domain academic_information --unit "Faculty of Computer and Mathematical Sciences" --academic-year 2027/28 --method hybrid --offline
```

The query can also state a year such as 2027 entry or 2025/26; it is extracted into
the filters. Entry year is a calendar year. Academic year is a teaching-year span;
September 2027 maps to 2027/28, whereas January 2027 would map to 2026/27. January
entry is not inferred where no such page was collected.

Results report entry_year, entry_term, year_basis, programme_code and cohort.
Response metadata includes year_filters, available_academic_years and
requires_year_clarification. Missing dated coverage returns no_year_specific_evidence.
The --allow-undated option is for background only; it does not establish applicability.

The 129 attempted 2026 entry-page versions were unavailable and were not indexed.
September 2026 admissions versions remain unavailable. Separately collected
January 2027 pages describe that intake in academic year 2026/27; do not use them
as proof of September 2026 cohort requirements, or replace either with 2027/28 pages.

programme_specific_coverage now indicates matching programme information in the
filtered candidates; it does NOT mean full programme regulations are present.
programme_requirements_coverage indicates that a matching PRD version exists in
the filtered candidates; verify its intake/pathway clauses. Programme pages provide published admissions/credit/curriculum
details and may include subject-to-approval conditions; preserve those conditions.

The dated faculty lists are transparently labelled local compilations of verified
downloaded official programme pages. They are not independent official PRDs or a
complete historical census. The year collection manifest logs unavailable requests.
Run scripts/check_year_retrieval.py to verify year isolation and missing-year handling.

## Extended public sources

Downloads and their audit manifest are in `files/extended_resources/`.
PRD academic years identify document versions; cohort and calendar entry year are
not automatically inferred. Undated subject forms and service pages remain undated,
and strict-year filters exclude them. A subject form does not prove the subject is
offered this semester or counts toward a particular degree. Subject-code questions
prefer subject descriptions; programme-code questions prefer a matching PRD.

```powershell
python -X utf8 -m policy_rag.retrieve --query "What is the prerequisite for COMP5926?" --method hybrid --offline --output data/demo_subject.json
python -X utf8 -m policy_rag.retrieve --query "What are the graduation credit requirements for programme 46010 in 2026/27?" --method hybrid --offline --output data/demo_prd.json
python -X utf8 -m policy_rag.retrieve --query "Where is the IT HelpCentre?" --domain student_services --method hybrid --offline --output data/demo_service.json
python -X utf8 scripts/check_extended_resources.py
```

Public service sources cover scholarship types, undergraduate hall policies,
health-service appointment guidance, campus clinics, IT support, orientation and
Library loan privileges, opening hours and regulations. They do not cover every service policy or
establish individual eligibility. Follow the cited official pages for updates.

## Verifier evidence gate

Run the included local example:

```powershell
python -X utf8 examples/verifier_example.py
python -X utf8 scripts/check_verifier.py
python -X utf8 -m policy_rag.verify --input data/verifier_demo_input.json --output data/verifier_cli_report.json
```

The Answerer must supply atomic `claims`, each with `text`, `evidence_id` and an
exact supporting `quote`. Optional payload fields are `academic_year`,
`programme_code`, `admission_cohort` and `retrieved_evidence_ids` (the allowed
retrieval IDs). Always supply that allowlist when integrating the agents. Citation
fields may also be supplied per claim and must match the canonical index exactly.

`policy_rag.verify.verify_claims(payload)` reads canonical evidence from the local
index, checks quotes, metadata scope and original-file SHA-256 hashes, and returns
canonical text/citations, errors and warnings. It never trusts Answerer-supplied
evidence text. Outcomes are `rejected` or `pending_semantic_review`; `approved`
is always false at this stage. No LLM key, network call or model download is needed.

The teammate's LLM Verifier should use `VERIFIER_INSTRUCTIONS`, inspect every
claim and canonical passage plus `retriever.context(evidence_id)`, and return a
supported/contradicted/insufficient_evidence decision with reasons and evidence IDs.
The Supervisor must not release an answer with rejected or unreviewed claims.
This gate does not implement an LLM Verifier, extract all claims from free text,
prove entailment or establish live currency/personal eligibility. A truthful quote
can still be attached to a false claim; the negative tests explicitly cover that.
