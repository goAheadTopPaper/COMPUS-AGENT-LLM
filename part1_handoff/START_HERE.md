# Your Part 1 is ready to hand over

## Retrieval improvement and test record

Read `data/part1_test_report.md` for the measured before/after results and all 20
questions. The full cited responses are saved in `data/part1_probe_after.json`.
Rerun the checks from the project folder:

```powershell
python -X utf8 scripts/check_part1_acceptance.py
```

This tests your allocated Part 1: source data, index, retrieval and evidence
metadata. Agent reasoning, final answer generation and school APIs remain your
teammates' integration work. You do not need to rebuild the delivered index.

## School-wide update: 20 November 2026

Open files/schoolwide/COLLECTION_README.md for the new complete catalogue audit.
The active collection now includes all 409 detail-page URLs discovered in the
saved central undergraduate/taught-postgraduate catalogues, plus the research
directory and linked public research pages. This does not mean every historical
programme or full PRD is available. There are 229 student-service sources overall.

List all programmes in a pathway without the retrieval top-k limit:

```powershell
python -X utf8 -m policy_rag.directory --student-type undergraduate --admission-pathway jupas --output data/all_jupas_programmes.json
```

Your teammate can call `from policy_rag.directory import list_programmes` for
listing questions, and PolicyRetriever for detailed questions. For undergraduate
requirements specify the admission pathway; for 2027 postgraduate entry specify
January or September. Share the latest output/part1_handoff.zip.

## 1. Find the downloaded documents

Open files/extended_resources/ in this project:

- programme_requirements/: 13 validated 2026/27 PRD PDFs.
- subject_descriptions/: 75 Computing subject PDFs.
- programme_guidance/: four public curriculum/FAQ/subject-list pages.
- student_services/: 12 active public service pages; the excluded 2012/13 Library handbook is also preserved locally for audit.
- COLLECTION_README.md: programme-code inventory, dates, exclusions and unresolved links.
- download_manifest.json: exact URLs, capture dates, hashes and validation outcomes.

The entire active collection now has 969 sources and 12,254 cited passages.
The generated index has already been rebuilt. You do not need to download or process these files again.

## 2. Try one question in your current PowerShell

Run this from the LLMproject folder:

```powershell
python -X utf8 -m policy_rag.retrieve --query "What is the prerequisite for COMP5926?" --method hybrid --offline --output data/demo_subject.json
```

Open data/demo_subject.json. The first evidence should cite page 1 of COMP5926,
with COMP5925 Metaverse Project I as the prerequisite. Its revision date is Dec 2022;
it is the public form served by the official linked URL at capture time, not proof of a 2026/27 offering.

## 3. Hand over your work

Send output/part1_handoff.zip to your teammates. It contains the active original
documents, index, scripts, reports and integration instructions. They should start
with README.md. The model weights are not bundled; first semantic use on a new
machine requires the dependency installation and model download explained there.

Suggested handoff message:

> Part 1 is updated: 969 sources and 12,254 cited passages, including 13 public
> 2026/27 PRDs, 75 Computing subject forms and 229 service sources. Use PolicyRetriever
> with policy, academic_information or student_services. Please preserve the year,
> cohort and source warnings. Full programme/cohort coverage and live personal
> records are not part of this dataset. See COLLECTION_README.md for remaining gaps.

## 4. Be precise about dates in the presentation

- The earlier extension was downloaded on 19 November 2026; the school-wide catalogue/service expansion was downloaded on 20 November 2026.
- The 2026/27 university handbook and ten registration guides matched the public PDF bytes in the 19 November 2026 currency check.
- 2024/25 and 2025/26 handbooks are historical versions, retained for year-specific questions.
- September 2027 admissions pages are labelled 2027/28; they cannot substitute for 2026/27 rules.
- Undated subject forms and service pages are snapshots, not automatically valid for every year.
- 18 FAQ articles could not be automatically compared with live JavaScript-rendered answer text.
- Five PRD links were not indexed because four PDFs reported encryption and one returned an HTML viewer.
- Coverage is partial. Do not present this as answering every question about PolyU.

All nine development check suites passed, including the new 20-question
passage-level evaluation. These are development retrieval checks,
not a held-out answer-quality benchmark. Your teammates still need to test agent
integration and generated answers using the supplied evidence.

## 5. Give the evidence checker to the Verifier teammate

```powershell
python -X utf8 examples/verifier_example.py
python -X utf8 scripts/check_verifier.py
```

The demo writes data/verifier_demo_input.json and data/verifier_demo_report.json.
The checker validates citations, quotes, source files and explicit year/programme
scope. It deliberately returns pending_semantic_review when those checks pass.
Your teammate must connect the LLM Verifier to check whether each claim actually
follows from the cited evidence. See the Verifier evidence gate section in README.md.
The updated ZIP includes this code, example and test report.
