# Individual Contribution Statement

Course: COMP5584  
Project: Multi-Agent Campus Information Assistant  
Group ID: \[To be completed by the group]

Each member should add a separate section with their full name, student ID, responsibilities, completed work, and how their component connects with other members' work. Confirm that each description matches the final submitted version. Replace the remaining placeholders before submission.

### Cheung Kwan Kit — 26007063G

GitHub username: cheungkk704  
Responsibility: Policy RAG, source preparation, and evidence retrieval

I developed the Policy RAG component for the campus information assistant. My work included collecting and organising university regulations, programme information, subject descriptions, and student-service documents; extracting traceable passages; and implementing persistent indexing and retrieval. I added academic-year and programme-scope filtering, source citations, evidence identifiers, and clarification indicators to support appropriately scoped retrieval.

I also implemented evidence-integrity checks for source hashes, quotations, and citation metadata. I tested retrieval behaviour using representative questions and unsupported requests, improved retrieval for identified failure cases, and prepared integration documentation and handoff materials.

My component supplies structured evidence to the group's Policy/Supervisor workflow. It supports the Answerer and Verifier by providing cited passages, scope information, and provenance checks. These checks support the Verifier's review; semantic assessment of generated answers is performed by the separate Verifier component.

As the RAG component provided evidence retrieval needed for downstream integration, I completed and handed it over to my teammates early so they could proceed with their modules. My teammates subsequently uploaded my contribution to the shared GitHub repository on my behalf, so the repository's commit authorship does not directly reflect my authorship of this component.

## Additional member — replace with full name and student ID

GitHub username: \[Optional]  
Responsibility: \[Module or component]

\[Describe your completed work and deliverables. Explain how your component interacts with or supports other members' modules. Duplicate this section for each remaining member.]



## FANG JUNNAN — 26056429g

**Responsibility:** Answerer Agent, Verifier Agent, and module testing

I developed the Answerer and Verifier modules for the Multi-Agent Campus Information Assistant. The Answerer combines evidence from the Policy and Schedule agents into a draft, linking each factual claim to an evidence ID and a supporting quotation. The Verifier checks that the cited quotations appear in the supplied evidence, then uses a separate model call to assess whether the evidence supports the claims and whether any part of the question remains unanswered.

I documented the input and output formats and provided scripts for offline and live-model testing. I tested the policy evidence interface using a result from the group's Policy RAG module and its source-integrity checker. I also ran three tests with DeepSeek using simulated schedule data. The module approved a correct answer, rejected a draft with an incorrect exam time despite an accurate quotation, and flagged insufficient evidence when the exam venue was missing.

The two modules are called by the Supervisor after evidence collection. They return a verified answer with citations when the draft passes, or a structured report that helps the Supervisor decide whether to revise the draft, retrieve more evidence, or ask the user for clarification.

## XU JINGXIANG — 26047724g

My main contribution to this project was the implementation of three agents—Supervisor Agent, Policy Agent, and Schedule Agent—and their integration with the frontend and data sources. I focused on connecting the individual components into a functional workflow that supports user questions, evidence retrieval, answer generation, and verification.

For the Supervisor Agent, I implemented question routing, task dispatch, evidence aggregation, bounded retries, and clarification handling. It determines which retrieval branches are needed and coordinates the existing Answerer and Verifier components. For the Policy Agent, I integrated the provided Part 1 retrieval system, preserving source citations, academic-year restrictions, clarification flags, and evidence integrity checks. For the Schedule Agent, I connected the public PolyU eStudent APIs to retrieve course information and teaching arrangements, including times, classrooms, and applicable teaching weeks.

I also addressed several integration challenges. These included inconsistent configuration parsing, incompatible module interfaces, course-name matching, and differences between documented and actual API responses. I implemented programme-name normalization and fuzzy matching, as well as catalogue-grounded semantic matching for Chinese course nicknames and abbreviations. Furthermore, I enabled university-wide course searches without requiring users to specify their programme and added automatic teaching-week calculation using the official academic calendar.

On the frontend, I connected the Streamlit interface to the agent pipeline and improved error reporting, citation display, and execution traces. I also added interactive clarification controls so users can select a course or provide supplementary information while retaining their original question. Finally, I conducted automated regression tests and real API and model checks to validate the integrated workflow.

## JIAO RUIKANG — 26103438g

GitHub username: J3rk

**Responsibility:** User interface, shared agent contract, and evaluation

I designed and implemented the Streamlit interface. Instead of a single chat window, it shows the answer beside a live agent trace, so delegation, retrieval, answer drafting, verification and retry appear as separate visible events, while refusal and clarification are explicit states rather than silent failures. Each claim links to an expandable evidence card giving the source title, PDF page, section and the original excerpt.

I defined the data contract shared across the group (Evidence, TaskPlan, RunContext and the authority ranking used to resolve conflicting sources), and implemented the adapter from the Part 1 retriever to that contract. It preserves the evidence identifier, page, section and applicability warnings that the Verifier requires, and exposes adjacent passages for clauses that continue across pages.

I built a 24-question benchmark covering policy, programme, subject and student-service queries, with a one-command runner reporting Recall@5 of 95% (19/20), a correct-refusal rate of 100% (3/3) and a median retrieval latency of 7 ms. Testing also surfaced several defects that only appear at integration time, including retrieval that returned nothing for Chinese queries, a semantic backend that fell back to empty results without raising an error, and a provenance gate that rejected all answers when original source files were absent. I recorded and produced the demo video. The interface was later extended by Xu Jingxiang with interactive clarification controls and additional error reporting.

## CHEN HONGTING — 26108188g

GitHub username: tonyc6  
Responsibility: Agent execution contract, evidence integration, and joint acceptance

I built the execution and evidence-contract layer that the delivered callable API runs on, connecting the Supervisor's routing decision to the Answerer/Verifier pair. In the final repository this module is `supervisor_compat.py`: it accepts a plan, dispatches only the branches the plan requests through injected callables, runs evidence collection, answer generation and verification in that order, and converts the Verifier's report into a result the interface can display. `supervisor.py` imports and re-exports `run` from it as the delivered callable API, and `scripts/check_pipeline.py` drives the whole pipeline through `supervisor.run`.

Three decisions shaped that layer. A branch may be not requested, succeed with no evidence, or raise; I kept these as distinct states (`not_called`, `empty`, `ok`, `failed`) so an empty result is never presented as a failed or unasked query. The retry allowance is one per question and shared across branch failure, Verifier rejection and model exception, with already-successful branches reused on retry. Above all, the unverified draft never leaves the module: only `passed` with `approved` returns an answer and its sources, and exception text is masked so credentials cannot reach logs or the interface.

I also wrote the Policy adapter (`policy_adapter.py`, `build_policy_search`), which the pipeline check and the acceptance suite use. It preserves Part 1's complete return value — status, academic-year filters, limitations and every clarification flag — rather than only the result list, because those flags determine whether the agent should ask the user a clarifying question. It also appends adjacent cross-page passages with stable, deduplicated evidence IDs, so a clause continuing onto the next page can still be cited. Separately, I wrote an independent client for PolyU's public eStudent subject endpoints (`subject_api.py`) and established against COMP5926 that prerequisite constraints exist only in the per-subject detail response, while the search summary always returns an empty constraint map — so prerequisite evidence is valid only when read from the detail endpoint.

The Schedule branch needed a comparable contract, so `schedule_evidence.py` normalises timetable rows into the citation-ready list the Answerer must quote: stable `schedule:` identifiers, and course, date, time, timezone and room stated explicitly in the quoted text. Records are built through a field whitelist, so Canvas tokens, student numbers and e-mail addresses cannot enter the model input. Date-only events are not given an invented `00:00`; a missing timezone is completed as Asia/Hong_Kong but recorded as a warning; identifier collisions receive a content-hash suffix, so two different rooms for the same course are not merged into one.

To confirm the components worked as one pipeline, I wrote the joint acceptance suite (`test_integration.py`, 7 tests), covering regulation-only, timetable-only, mixed queries requiring both citation types, insufficient evidence that must not expose the draft, a correct citation paired with a wrong time in the draft, and clarification-flag and verification-gate passthrough. Together with the module tests this is 58 automated tests, and the pipeline was verified under both the flat repository layout and the packaged `answer_verifier/` layout.

My modules exchange plain JSON-serialisable dictionaries and lists, so they bind to the shared contract layer defined by Jiao Ruikang without changes on either side, and the Answerer and Verifier written by Fang Junnan are called unchanged. The Supervisor Agent, routing and live application path in the final version were implemented by Xu Jingxiang; my modules supply the callable execution API the pipeline check runs, the Policy adapter it uses, and the evidence format for the Schedule branch.
