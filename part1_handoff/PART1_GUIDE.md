# Part 1 handoff: policy data and retrieval

Target academic year: **2026/27**. Admission cohort is separate and not assumed.
Current collection: **969 sources and 12,254 cited passages**, including university
rules and information from 39 academic units. It does not contain every programme's
cohort-specific graduation requirements. Original downloads are unchanged.
Source folders include `files/School Regulation/`, `files/faculty wise rules/`,
`files/year_specific/`, `files/extended_resources/` and `files/schoolwide/`.
Faculty pages with adequate extracted text are indexed through the download manifest.
Three low-text faculty pages remain excluded for visual review.
See README.md for the current API contract and one-command rebuild instructions.

## 1. Install the two extraction packages

Open PowerShell in the LLMproject folder:

```powershell
python -m pip install -r requirements-semantic.txt
```

The Python environment used to author this project already contains these packages;
the normal system Python may need the command above. A teammate must install them
when rebuilding extraction. BM25/TF-IDF search needs only Python; semantic/hybrid
search needs sentence-transformers and cached model weights.

## 2. Rebuild the catalogue (only if downloads or metadata changed)

```powershell
python scripts/prepare_source_list.py
python scripts/build_source_catalogue.py
```

Edit confirmed metadata in data/source_metadata_overrides.csv. Unknown capture
dates stay blank. Adding new programme documents also requires adding classification
rules to build_source_catalogue.py; it deliberately rejects unclassified documents.

## 3. Extract and split

```powershell
python -m policy_rag.prepare
```

Outputs: documents.jsonl, chunks.jsonl, extraction_report.json in data/.
FAQ bodies are extracted from the article content container, not the index or
related-question lists. PDFs retain physical PDF page numbers and detected printed
page numbers. HTML tables retain cell separators, but schedules require manual
row/header checking. PDF screenshot contents have not been OCRed.

Policy passages use at most 350 words with 60-word overlap; faculty passages use
140 words with 25-word overlap, except programme listings, which preserve complete
name/code entries in groups of up to about 800 words. Page boundaries remain intact for citations. Use context() to
inspect adjacent passages where clauses continue across pages. Check exceptions
and eligibility manually before relying on a passage.

## 4. Build the semantic index

```powershell
python -m policy_rag.retrieve --build --model sentence-transformers/all-MiniLM-L6-v2 --offline
```

Creates data/policy_index.sqlite. It stores passages, provenance, token statistics
and both normalized TF-IDF and neural semantic vectors. BM25, cosine vector ranking
and rank fusion run locally without keys. --offline requires cached model weights;
omit it on a new machine to allow the first model download.
This small SQLite store uses exact scoring, not an approximate vector-search engine.

## 5. Try retrieval and checks

```powershell
python -X utf8 -m policy_rag.retrieve --query "Can I drop a subject after the add drop period?" --student-type taught_postgraduate --top-k 3
python scripts/check_part1.py
python scripts/check_faculty_integration.py
```

Methods: bm25, vector, semantic, hybrid. The vector method means TF-IDF cosine.
Hybrid fuses BM25 and neural semantic rankings when neural vectors are built;
otherwise it uses TF-IDF. Set --domain policy or --domain academic_information
explicitly when integrating agents; automatic keyword routing is a fallback.
Development checks are NOT a held-out benchmark. Inspect failures in
data/retrieval_checks.json, then have a teammate independently label 15-20 fresh
questions against the original sources for final evaluation. Do not claim all
retrieved passages are correct based on a source-level Hit@5 score.

The additional 20-question passage-level development check is available with
`python -X utf8 scripts/check_part1_acceptance.py`. Read
`data/part1_test_report.md` for before/after evidence ranks, multi-part question
coverage and the full local source/index integrity audit. These checks are
limited to Part 1 and do not grade the Answerer, Verifier or live API agents.

## 6. Optional: add actual semantic embeddings

Do this after the baseline runs, if the group needs neural embeddings:

```powershell
python -m pip install sentence-transformers
python -m policy_rag.retrieve --build --model sentence-transformers/all-MiniLM-L6-v2
python -m policy_rag.retrieve --query "Can I leave a course after the deadline?" --method semantic
```

First use downloads model weights and dependencies. The semantic backend has now
been built and exercised on ten saved development questions. See
data/test_record_review.md for the qualitative review and its limitations.
This example model is for English. Do not promise Chinese retrieval without testing
a suitable multilingual model or a translation stage. Long passages are encoded
as overlapping token windows and mean-pooled, then normalized. Rebuilding without --model restores
the lexical baseline and replaces generated neural vectors.

API reference: https://sbert.net/docs/quickstart.html

## 7. Give your teammates the retrieval interface

```python
from policy_rag.retrieve import PolicyRetriever

retriever = PolicyRetriever()
response = retriever.search(
    query="Can I drop a subject after the deadline?",
    top_k=5,
    academic_year="2026/27",
    student_type="taught_postgraduate",
    programme_code=None,
    admission_cohort=None,
    method="hybrid",
    knowledge_domain="policy",
)
```

Student types: undergraduate, full_time_undergraduate, part_time_undergraduate,
postgraduate, taught_postgraduate, research_postgraduate.

Response contains results with evidence_id, source_id, text, citation (title,
URL, PDF page, printed page, section), relevance score and applicability warnings.
Optional source_type filter: handbook, faq, procedure, schedule, academic_unit_information.
knowledge_domain accepts policy, academic_information, all, or auto (default).
For faculty information, set knowledge_domain="academic_information" and optionally
unit="Department of Computing" or faculty="Faculty of Engineering". Exact official
names are required; matching is case insensitive. Returned metadata includes unit,
faculty, source domain, page type and capture time.
Optional subject_codes filter: list of codes; requires an exact code in a passage.
Use retriever.context(evidence_id) for adjacent passages from the same source.

Scope filtering excludes explicitly incompatible student groups, years, programmes
and interpretable cohort ranges. Unknown metadata remains available with warnings;
mixed handbook pages require clause-level applicability review by the verifier.
programme_specific_coverage=false means the corpus has no matching programme
document; general evidence can still be returned. This is not proof of eligibility.
Positive relevance scores do not establish answerability. Unanswerable questions
can still retrieve related evidence; the Answerer/Verifier must identify missing facts.

Examples: examples/policy_agent_example.py.

## 8. Hand off and report honestly

Share the refreshed output/part1_handoff.zip, which includes both requirement files,
original sources, manifests, data, code, guides and examples. Model weights are not bundled.
Original PDFs/HTML are needed for rebuilding and visual checking. Saved webpage
resource folders are not indexed. No credentials are required for the baseline.

Report: 969 catalogued sources (including 11 derived lists); 12,254 passages; 39 academic units; metadata
filters; lexical baseline; semantic retrieval; development retrieval checks. Partial programme PRD coverage,
unknown dates, screenshot-only content and mixed-source eligibility are limitations.

## Save query results safely on Windows

```powershell
python -X utf8 -m policy_rag.retrieve --query "Your actual question" --method semantic --top-k 5 --output data/test_new.json
```

Use --output instead of piping Unicode output through Windows PowerShell 5.1.
The original ten terminal records were backed up and regenerated as valid UTF-8.

## Faculty ranking improvements

Programme-list questions prefer Programmes pages, contact questions prefer Contact
pages, and overview questions prefer Overview pages when matching evidence exists.
The result can contain fewer than top_k entries to avoid unrelated filler. The
FCMS development query now returns its complete cleaned 13-entry programme listing
first. This tests the saved snapshot, not current admission availability.
Browser/search/cookie notices and embedded homepage news components are excluded
from the processed faculty text. Raw downloaded files are unchanged.

## Query a specific academic/entry year

See README.md for current commands. Explicit --academic-year uses strict dated
evidence; unknown-year faculty pages are excluded. For admissions questions use
--entry-year, e.g. --programme-code 61038 --entry-year 2027. Entry year is not the
same as academic year or prior students' admission cohort.

Policy years covered: 2024/25, 2025/26, 2026/27. Programme detail coverage includes
January 2027 / academic year 2026/27 and September 2027 / academic year 2027/28.
September 2026 admissions versions remain unavailable. Missing-year requests
return no_year_specific_evidence. Detailed
admissions pages are not full PRDs. Selected 2026/27 PRDs are now included separately;
programme_requirements_coverage reports a matching PRD version in filtered candidates.

Files are in files/year_specific/. Its manifest records verified visible years,
source URLs, hashes, capture dates and unsuccessful requests. Eleven derived
faculty lists compile downloaded programme pages with original per-programme links.

## Programme-page cleanup

Related-programme cards, admissions-event promotions and general navigation are
excluded. Each main programme field has its own section, keeping summary/deadlines,
curriculum, credits, fees and entry requirements distinct. Queries prioritise the
relevant section, and citations identify it. Original pages and year labels are unchanged.

## Policy scope ranking

Handbook passages now follow lettered subsection boundaries and expose policy_topic
and policy_subsection. Subject-withdrawal questions prefer Withdrawal of Subjects;
programme-withdrawal questions prefer Withdrawal of Study. Comparison questions
can retain both. Ambiguous withdrawal requests set requires_policy_clarification.
The response reports preferred_policy_topics and policy_topic_preference_applied.
This is a transparent heuristic, not a learned reranker or a guarantee of eligibility.
PDF completeness flags are conservative because clauses may continue across pages.

## Added public documents and services

See `files/extended_resources/COLLECTION_README.md` for the new download inventory,
programme codes and unresolved links: 13 PRDs, 75 Computing subject forms, four
programme guidance pages and 12 student-service sources. Use the examples at the
end of README.md. No further download or rebuild is needed to use the supplied index.
Your teammate should reuse PolicyRetriever and choose the domain explicitly.
