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
