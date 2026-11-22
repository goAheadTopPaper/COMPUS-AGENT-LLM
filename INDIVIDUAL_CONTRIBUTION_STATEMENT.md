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

