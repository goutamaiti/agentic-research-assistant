# PROJECT_CONTEXT.md

# Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction

**Project domain:** Research and Academia\
**Application type:** Single-paper Agentic NLP Research Assistant\
**Specification status:** Planning baseline approved; implementation not
yet started\
**Intended implementation partner:** Claude\
**Document role:** Master project specification and implementation
reference

------------------------------------------------------------------------

## 0. Instructions to Claude

You are implementing a college-level NLP mini-project. Treat this
document as the authoritative project specification.

### How to work

1.  Read this document fully before making implementation decisions.
2.  Implement incrementally, one development phase at a time.
3.  Do not generate the entire application in one coding pass.
4.  Before each phase, inspect the existing repository and summarize the
    planned changes.
5.  Implement the smallest complete vertical slice, run tests, fix
    failures, and document the result.
6.  Do not begin the next phase while the current phase has unresolved
    critical failures.
7.  Maintain `DEVELOPMENT_LOG.md` with:
    -   completed tasks;
    -   files changed;
    -   commands run;
    -   tests and results;
    -   known bugs and limitations;
    -   next recommended task.
8.  Keep `PROJECT_CONTEXT.md` as the stable requirements document. Do
    not silently rewrite approved requirements.
9.  If a technical change is necessary, explain the reason, alternatives
    considered, impact, and migration plan. Do not change a major
    technology or scope decision silently.
10. Do not invent project requirements, research-paper facts, citations,
    evaluation results, or performance claims.
11. Do not hardcode API keys, credentials, local absolute paths, or
    machine-specific configuration.
12. Use typed interfaces, clear module boundaries, logging, tests, and
    meaningful error messages.
13. Prefer simple, dependable implementations over unnecessary
    infrastructure or elaborate autonomous-agent behaviour.
14. Never claim a feature is complete until its acceptance criteria and
    tests have been checked.

### Important scope rule

This is a **single-paper research analysis application**. One analysis
workspace processes one academic research paper. A user may create a
separate workspace for another paper, but information from separate
workspaces must not be combined, compared, or used to produce
cross-paper conclusions.

There is no multi-paper analysis roadmap in this project specification.

------------------------------------------------------------------------

# 1. Project overview

## 1.1 Project title

**Agentic RAG Framework for Automated Domain-Specific Knowledge
Extraction**

## 1.2 Domain

Research and Academia.

## 1.3 Problem statement

Academic research papers contain valuable information about research
problems, objectives, motivations, prior work, methodologies,
algorithms, datasets, experimental results, limitations, and future
directions. Extracting and organizing this information manually is
time-consuming. Conventional document question-answering and
summarization tools may provide fluent responses but do not necessarily
produce a complete, consistently structured analysis or verify each
extracted claim against its source.

The project proposes an agentic Retrieval-Augmented Generation (RAG)
framework that processes one academic research paper at a time. It
extracts structured research knowledge, retains page- and section-level
evidence, verifies extracted claims against the original document, and
provides a conversational assistant that answers questions using the
uploaded paper.

## 1.4 Proposed solution

The application accepts one academic PDF, processes its content, builds
a searchable document index, extracts the defined research categories,
verifies factual claims against original passages, stores the results,
and presents them through a dashboard, conversational interface, and
downloadable report.

The application combines:

-   PDF text extraction and OCR where necessary;
-   section-aware document chunking;
-   semantic and keyword retrieval;
-   LLM-based structured knowledge extraction;
-   evidence-based claim verification;
-   controlled LangGraph orchestration;
-   persistent structured storage;
-   source-grounded conversational question answering.

## 1.5 Intended users

-   Undergraduate and postgraduate research students;
-   PhD scholars;
-   academic researchers;
-   faculty members and research supervisors.

The initial application is designed for English-language academic
research papers.

------------------------------------------------------------------------

# 2. Scope lock

## 2.1 In scope

1.  One academic research PDF per analysis workspace.
2.  PDF validation and upload.
3.  Text-based PDF processing.
4.  OCR fallback for scanned pages where feasible.
5.  Page and section identification.
6.  Metadata extraction.
7.  Section-aware chunking and embedding generation.
8.  ChromaDB vector indexing.
9.  BM25 keyword indexing.
10. Hybrid retrieval and result fusion.
11. Extraction of all 12 primary categories.
12. Four additional intelligence capabilities.
13. Claim-level evidence traceability.
14. Evidence-based verification.
15. Bounded retries for incomplete or unsupported extraction.
16. Structured JSON output.
17. Conversational question answering about the current paper.
18. Page-level citations and supporting passages.
19. Persistent storage of documents and analysis.
20. PDF, DOCX, and JSON report export.
21. Software testing and NLP evaluation against manually annotated
    references.

## 2.2 Explicitly out of scope

Do not implement these features:

-   Multi-paper analysis or collections that combine papers;
-   cross-paper comparisons;
-   cross-publication relationship discovery;
-   research gap discovery across multiple publications;
-   contradiction detection between different papers;
-   automatic academic paper discovery or web browsing;
-   literature review generation from multiple papers;
-   Neo4j or a dedicated graph database;
-   multi-user collaboration;
-   mobile applications;
-   custom LLM training or fine-tuning;
-   training a new embedding model;
-   unrestricted autonomous agents;
-   autonomous actions outside the uploaded document.

A separate paper may be uploaded and analyzed in a separate workspace.
The application must keep workspaces isolated.

## 2.3 Initial constraints

  -----------------------------------------------------------------------
  Setting                             Initial requirement
  ----------------------------------- -----------------------------------
  Documents per analysis              1 PDF

  Initial language                    English

  Maximum PDF size                    30 MB, configurable

  PDF types                           Text-based and scanned

  Password-protected PDF              Reject with a clear message in
                                      initial version

  Damaged/unreadable PDF              Reject or report partial processing

  Model inference                     Cloud API

  Embedding inference                 Local Sentence Transformers model

  Vector storage                      Local persistent ChromaDB

  Application database                SQLite

  Initial deployment                  Local development

  Verification retries                Maximum 2 retries per failed
                                      extraction task, configurable
  -----------------------------------------------------------------------

These are initial engineering constraints. Do not describe them as
universal technical limits of the selected models or libraries.

------------------------------------------------------------------------

# 3. Functional requirements

  -----------------------------------------------------------------------
  ID                      Requirement             Priority
  ----------------------- ----------------------- -----------------------
  FR-01                   Upload one academic PDF Must
                          into an analysis        
                          workspace               

  FR-02                   Validate file type,     Must
                          size, integrity, and    
                          readability             

  FR-03                   Extract page-wise       Must
                          document text           

  FR-04                   Detect scanned pages    Must
                          and attempt OCR         

  FR-05                   Identify paper sections Must
                          and subsections where   
                          possible                

  FR-06                   Extract available       Must
                          publication metadata    

  FR-07                   Chunk document content  Must
                          while preserving page   
                          and section references  

  FR-08                   Generate embeddings and Must
                          index chunks            

  FR-09                   Support semantic and    Must
                          keyword retrieval       

  FR-10                   Extract all 12 primary  Must
                          knowledge categories    

  FR-11                   Generate technical      Must
                          methodology breakdown   

  FR-12                   Identify author-claimed Must
                          and system-inferred     
                          contributions           
                          separately              

  FR-13                   Extract technical       Must
                          terminology and         
                          abbreviations           

  FR-14                   Attach source evidence  Must
                          to factual claims       

  FR-15                   Verify claims against   Must
                          original source         
                          passages                

  FR-16                   Distinguish verified,   Must
                          partially supported,    
                          unsupported,            
                          contradicted, and       
                          unverifiable claims     

  FR-17                   Retry incomplete        Must
                          extraction within       
                          configured limits       

  FR-18                   Validate final output   Must
                          using Pydantic          

  FR-19                   Persist analysis and    Must
                          processing metadata     

  FR-20                   Answer questions about  Must
                          the current paper       

  FR-21                   Display source page     Must
                          references and evidence 
                          passages                

  FR-22                   Preserve conversation   Must
                          history within a paper  
                          workspace               

  FR-23                   Generate a research     Must
                          analysis report         

  FR-24                   Export JSON, PDF, and   Must
                          DOCX                    

  FR-25                   Show meaningful         Must
                          processing status and   
                          errors                  

  FR-26                   Delete a paper and its  Must
                          associated              
                          application/vector data 
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 4. Knowledge extraction specification

The system must extract the following 12 primary categories and four
additional capabilities.

## 4.1 Primary categories

### 1. Paper metadata

Extract, when available:

-   full title;
-   author names;
-   publication year;
-   journal or conference;
-   DOI;
-   original abstract;
-   keywords;
-   detected document language.

Do not infer missing metadata. Use an explicit `not_found` state.

### 2. Abstract

Retain the original abstract separately from the system-generated
summary. Extract its stated problem, approach, principal findings, and
conclusion where available.

### 3. Research problem

Extract:

-   problem statement;
-   application context;
-   problem significance;
-   specific challenge being addressed;
-   evidence in the paper that establishes the problem.

### 4. Research objectives

Extract the main objective and individual specific objectives. Keep
objectives distinct from claimed contributions and from results.

### 5. Research motivation

Extract why the authors conducted the research, the practical or
theoretical need, and the shortcomings or unresolved issues motivating
the work.

### 6. Literature background

Summarize the background and prior approaches discussed in the paper. Do
not claim that this is an exhaustive literature review. Preserve cited
approaches and their context where possible.

### 7. Methodology

Extract the overall research approach, workflow, methods, major stages,
implementation procedure, and experimental methodology.

### 8. Algorithms and models

For each algorithm or model, extract:

-   name;
-   category/type;
-   role in the research;
-   purpose;
-   implementation details;
-   reported parameters or configurations;
-   evidence.

### 9. Dataset and experimental setup

Extract, when reported:

-   dataset name;
-   source;
-   dataset size;
-   data characteristics;
-   train/validation/test split;
-   simulation or experimental environment;
-   hardware/software configuration;
-   experimental parameters;
-   evaluation protocol.

Do not invent dataset size, source, or configuration.

### 10. Results and findings

Extract:

-   qualitative findings;
-   numerical results;
-   evaluation metrics;
-   values and units;
-   experimental conditions;
-   comparison baselines;
-   observations;
-   conclusions drawn by the authors.

Retain context for every numerical result. A metric without its
conditions or definition may be misleading.

### 11. Limitations

Separate limitations explicitly acknowledged by the authors from
possible limitations inferred by the system. Never present an inferred
limitation as an author statement.

### 12. Future scope

Extract future research directions explicitly proposed by the authors.
Distinguish author-proposed future work from suggestions generated by
the system.

## 4.2 Additional intelligence capabilities

### A. Technical methodology breakdown

Convert the methodology into an ordered explanation. Each step should
include:

-   step number;
-   operation;
-   input;
-   process or technique;
-   output;
-   evidence references.

The system may explain technical steps in accessible language, but must
preserve the paper's meaning.

### B. Research contribution identification

Maintain two separate lists:

-   `author_claimed`: contributions explicitly stated or clearly claimed
    by the authors;
-   `system_inferred`: cautious interpretations inferred from the paper.

Every inferred contribution must be labelled as inferred and must have
supporting evidence. Do not present an inferred contribution as an
established novelty claim.

### C. Technical terminology

For each term, capture:

-   term;
-   abbreviation, if applicable;
-   definition or explanation;
-   context of use;
-   evidence references.

If the paper uses a term without defining it, the assistant may provide
a clearly labelled general explanation, but must distinguish that
explanation from the paper's own definition.

### D. Evidence traceability

Every factual claim should point to one or more evidence records. An
evidence record should preserve:

-   evidence ID;
-   associated claim ID;
-   PDF zero-based page index;
-   displayed page number if identifiable;
-   section name if identifiable;
-   exact supporting source text;
-   verification status;
-   verification explanation.

The physical PDF page index and printed page number are not necessarily
the same. Preserve both when available.

------------------------------------------------------------------------

# 5. Data and extraction schema

## 5.1 Schema design principles

1.  Use a hierarchical Pydantic schema.
2.  Give each factual claim a stable ID.
3.  Give each evidence passage a stable ID.
4.  Reference evidence by ID rather than duplicating long passages in
    every claim.
5.  Preserve the original source text.
6.  Separate extraction status from verification status.
7.  Separate author-stated information from system inference.
8.  Represent unavailable information explicitly.
9.  Store schema and model versions with each analysis.
10. Validate all LLM responses in application code.

## 5.2 Core status enums

Extraction status:

-   `extracted`
-   `not_found`
-   `partially_extracted`
-   `ambiguous`

Verification status:

-   `pending`
-   `verified`
-   `partially_supported`
-   `unsupported`
-   `contradicted`
-   `not_verifiable`

Origin:

-   `author_claimed`
-   `system_inferred`
-   `directly_extracted`
-   `system_explanation`

Use Python enums or Pydantic `Literal` fields. Do not accept arbitrary
status strings.

## 5.3 Recommended top-level JSON structure

This is the conceptual output contract. Claude must implement detailed
Pydantic models for each nested object.

``` json
{
  "schema_version": "1.0",
  "paper_metadata": {
    "title": null,
    "authors": [],
    "publication_year": null,
    "journal_or_conference": null,
    "doi": null,
    "abstract": null,
    "keywords": [],
    "document_language": null
  },
  "research_analysis": {
    "research_problem": {},
    "objectives": [],
    "motivation": {},
    "background": {},
    "methodology": {},
    "results": [],
    "limitations": [],
    "future_scope": []
  },
  "technical_analysis": {
    "algorithms_and_models": [],
    "dataset_and_experiments": {},
    "methodology_breakdown": [],
    "research_contributions": {
      "author_claimed": [],
      "system_inferred": []
    },
    "technical_terminology": []
  },
  "claims": [],
  "evidence_registry": [],
  "processing_metadata": {
    "document_id": null,
    "workflow_run_id": null,
    "model_id": null,
    "embedding_model_id": null,
    "prompt_version": null,
    "schema_version": "1.0",
    "index_version": null,
    "processing_status": null,
    "verification_summary": {}
  }
}
```

## 5.4 Standard claim object

``` json
{
  "claim_id": "CLM_001",
  "category": "algorithm",
  "claim_text": "The paper uses Proximal Policy Optimization.",
  "origin": "directly_extracted",
  "extraction_status": "extracted",
  "verification_status": "verified",
  "confidence": null,
  "evidence_ids": ["EVD_001"],
  "verification_explanation": "The cited passage explicitly identifies PPO."
}
```

Confidence is optional and must not be treated as a calibrated
probability unless calibration has been experimentally demonstrated.
Verification is a separate evidence-based decision.

## 5.5 Standard evidence object

``` json
{
  "evidence_id": "EVD_001",
  "claim_id": "CLM_001",
  "pdf_page_index": 5,
  "displayed_page_number": "4",
  "section_name": "Methodology",
  "source_text": "Exact supporting text from the paper.",
  "verification_status": "verified",
  "verification_explanation": "The source passage supports the extracted claim."
}
```

## 5.6 Missing information

A missing field should be represented explicitly, for example:

``` json
{
  "value": null,
  "status": "not_found",
  "evidence_ids": []
}
```

Do not use plausible guesses, common defaults, or general model
knowledge to fill a field that is absent from the uploaded paper.

## 5.7 Numerical findings

For numerical results, preserve as many of the following as the source
provides:

-   metric name;
-   numeric value;
-   unit;
-   experimental condition;
-   dataset/environment;
-   comparison baseline;
-   source passage;
-   page reference.

Do not compare or rank results without checking whether the experimental
conditions and metrics are comparable.

------------------------------------------------------------------------

# 6. Final technology stack

Use this as the approved baseline. Confirm package compatibility and
current supported APIs during Phase 1; do not blindly install unpinned
latest versions.

  ----------------------------------------------------------------------------------------------------
  Component               Selected technology                                  Responsibility
  ----------------------- ---------------------------------------------------- -----------------------
  Language                Python 3.12+                                         Backend and NLP

  LLM                     Google Gemini 3.8 Flash                              Extraction, reasoning,
                                                                               verification, Q&A

  Model ID                `gemini-3.8-flash`                                   Configurable
                                                                               environment setting

  LLM SDK                 Official Google GenAI Python SDK                     Model API access

  Orchestration           LangGraph                                            Workflow state, nodes,
                                                                               routing, retries

  Supporting framework    LangChain Core selectively                           Prompts and compatible
                                                                               utilities

  Embeddings              `sentence-transformers/multi-qa-mpnet-base-cos-v1`   Semantic
                                                                               representations

  Embedding runtime       Sentence Transformers                                Local embedding
                                                                               generation

  Vector database         ChromaDB                                             Persistent vector index

  Keyword retrieval       BM25 implementation                                  Exact-term retrieval

  Result fusion           Reciprocal Rank Fusion                               Combine retrieval
                                                                               rankings

  PDF processing          PyMuPDF                                              Text and page
                                                                               extraction

  OCR                     Tesseract                                            Scanned-page OCR
                                                                               fallback

  Optional PDF helper     pdfplumber                                           Supplementary table
                                                                               extraction if needed

  Validation              Pydantic                                             Typed structured data
                                                                               validation

  Backend                 FastAPI                                              REST API

  ORM                     SQLAlchemy                                           SQLite data access

  Migrations              Alembic                                              Database schema
                                                                               migrations

  Application database    SQLite                                               Documents, claims,
                                                                               evidence, chats, runs

  Frontend                React + Vite                                         User interface

  Styling                 Tailwind CSS                                         UI styling

  Reports                 ReportLab and python-docx                            PDF and DOCX export

  Testing                 pytest                                               Backend and pipeline
                                                                               tests

  Version control         Git and GitHub                                       Source control
  ----------------------------------------------------------------------------------------------------

## 6.1 LLM model selection

Primary model: `gemini-3.8-flash`.

Use it for:

-   structured extraction;
-   methodology explanation;
-   research contribution classification;
-   evidence verification;
-   conversational question answering;
-   report narrative generation.

Use one primary model initially to reduce integration complexity and
make evaluation consistent.

Model ID, provider settings, generation configuration, and timeout/retry
settings must be configurable through environment variables or a central
settings module.

Before coding against a specific API method, check the current official
Google GenAI SDK documentation. Prefer supported structured output with
a Pydantic/JSON Schema contract. Parse and validate the returned content
in application code.

Official references: - Gemini models:
https://ai.google.dev/gemini-api/docs/models - Structured output:
https://ai.google.dev/gemini-api/docs/structured-output - Gemini API
getting started: https://ai.google.dev/gemini-api/docs/get-started

Pricing, quotas, availability, free-tier terms, and data handling
policies can change. Do not hardcode pricing or promise free API usage.
Use public papers for initial development and review the provider's
current data-handling terms before using unpublished or confidential
research documents.

## 6.2 Embedding model and chunking

Selected model:

`sentence-transformers/multi-qa-mpnet-base-cos-v1`

Use it locally for question-to-passage semantic retrieval.

Important constraints:

-   Respect the model's maximum sequence length.
-   Begin with section-aware chunks of approximately 200--250 word
    pieces, then tune through retrieval experiments.
-   Start with approximately 30--50 word pieces of overlap where
    appropriate.
-   Do not split in the middle of a paragraph or table when a better
    boundary is available.
-   Avoid embedding large amounts of irrelevant references or repeated
    headers without a reason.
-   Store the embedding model ID and index version with the index.

The earlier 600-token chunk suggestion is superseded by this more
conservative starting point for the selected embedding model.

Model reference:
https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1

## 6.3 Retrieval strategy

Use hybrid retrieval:

1.  Semantic search through ChromaDB.
2.  Keyword search through BM25.
3.  Merge rankings with Reciprocal Rank Fusion.
4.  Optionally rerank candidates if evaluation demonstrates a meaningful
    improvement.
5.  Return source text with chunk ID, document ID, page index, displayed
    page number, and section.

Initial tunable settings:

  Parameter                          Starting value
  -------------------------- ----------------------
  Chunk target                 200--250 word pieces
  Chunk overlap                  30--50 word pieces
  Semantic candidates                             8
  BM25 candidates                                 8
  Initial fused candidates                 Up to 10
  Final evidence passages                   Up to 6

These are starting values, not established optimal settings. Evaluate
them on the test set.

## 6.4 Database decision

Do not use Neo4j. This project does not require a dedicated graph
database.

Use SQLite for application records and ChromaDB for semantic retrieval.
Link claims and evidence using stable IDs and relational tables.
Structured JSON is sufficient for the single-paper knowledge
representation.

Do not add FAISS as a second vector database. ChromaDB is the selected
vector store.

------------------------------------------------------------------------

# 7. Agent and component responsibilities

The system has a LangGraph coordinator and five specialized
processing/interaction components. Not every component must be an
autonomous LLM agent. Use deterministic Python services for parsing,
indexing, validation, persistence, and retrieval wherever possible.

## 7.1 Research Coordinator

**Role:** Controls the workflow.

Responsibilities:

-   maintain shared state;
-   start and sequence processing nodes;
-   route tasks;
-   handle conditional transitions;
-   enforce retry limits;
-   record status and errors;
-   determine when a workflow is complete;
-   avoid unnecessary model calls.

Do not implement an unrestricted autonomous loop.

## 7.2 Document Processing component

**Role:** Convert the PDF into a structured, source-preserving
representation.

Responsibilities:

-   validate PDF;
-   extract page-wise text;
-   detect pages with little or no extractable text;
-   run OCR fallback where appropriate;
-   identify section headings and hierarchy;
-   extract available metadata;
-   preserve tables where feasible;
-   create chunks with source mappings.

Use deterministic code for parsing and metadata extraction where
possible. LLM assistance may be used for ambiguous section
classification, but it must not replace basic PDF processing.

Output: - document metadata; - page records; - section hierarchy; -
chunks; - page and section mappings; - processing warnings.

## 7.3 Retrieval component / Retrieval Agent

**Role:** Find relevant passages for an extraction task or user
question.

Responsibilities:

-   receive a focused query;
-   perform semantic retrieval;
-   perform BM25 keyword retrieval;
-   combine rankings;
-   apply section filters where appropriate;
-   return relevant passages and source metadata;
-   indicate when retrieval is insufficient.

Retrieval should be primarily a deterministic service/node. Do not add
an LLM decision loop unless a specific retrieval task requires it.

## 7.4 Knowledge Extraction Agent

**Role:** Turn source passages into structured research knowledge.

Responsibilities:

-   extract the 12 primary categories;
-   extract the four additional capabilities;
-   use category-specific prompts and Pydantic output models;
-   attach evidence references;
-   identify missing and ambiguous information;
-   distinguish author statements from system inferences;
-   preserve numerical context;
-   avoid unsupported completion.

Process categories in manageable groups or section-aware tasks. Do not
force the entire paper into one enormous prompt if that risks truncation
or omissions.

## 7.5 Verification Agent

**Role:** Check extracted claims against original source passages.

Responsibilities:

-   receive claims and evidence references;
-   retrieve the original passage;
-   compare claim and source meaning;
-   check entities, names, numbers, units, and context;
-   identify partial support;
-   identify unsupported or contradicted claims;
-   check page/section attribution;
-   provide an explanation;
-   request targeted retrieval/re-extraction when appropriate.

Use a combination of deterministic checks and LLM-based evidence
assessment. Do not rely only on an LLM asking itself whether its prior
response was correct.

## 7.6 Research Assistant Agent

**Role:** Answer questions about the currently analyzed paper.

Responsibilities:

-   interpret the user's question;
-   use verified structured knowledge where appropriate;
-   retrieve additional passages when needed;
-   generate source-grounded answers;
-   provide page citations and supporting passages;
-   maintain conversation context within the same workspace;
-   state when the paper does not provide sufficient evidence.

The assistant must not present general pretrained knowledge as a fact
from the uploaded paper. If it provides a general explanation, label it
separately from paper-derived content.

------------------------------------------------------------------------

# 8. LangGraph workflows

Implement two separate workflows.

## 8.1 Analysis workflow

1.  Receive document ID and stored file path.
2.  Validate the document.
3.  Process pages, sections, and metadata.
4.  Chunk and index document content.
5.  Run category-specific retrieval and extraction tasks.
6.  Combine outputs into the unified schema.
7.  Verify extracted claims.
8.  Route failed or insufficient claims for targeted
    retrieval/re-extraction.
9.  Enforce maximum two retries per failed task.
10. Mark unresolved claims with the correct status.
11. Validate the complete output with Pydantic.
12. Persist extraction, claims, evidence, and processing metadata.
13. Mark the analysis complete or partially complete.

A missing category must not fail the entire paper analysis. Preserve
partial completion and explain what was not found or could not be
processed.

## 8.2 Conversational Q&A workflow

1.  Receive workspace/document ID and question.
2.  Confirm that the requested document has completed indexing.
3.  Inspect verified structured knowledge for relevant facts.
4.  Perform hybrid retrieval for additional evidence.
5.  Build a grounded answer context.
6.  Generate the answer.
7.  validate citation references against retrieved evidence IDs.
8.  Return answer, page references, and supporting passages.
9.  Save conversation history.

If there is insufficient evidence, say so. Do not fabricate a response.

## 8.3 Retry rules

-   Maximum two retries per failed extraction task.
-   Use targeted queries, not a complete re-run of the whole paper.
-   Log every retry and its reason.
-   Do not retry deterministic validation failures indefinitely.
-   If still unresolved, retain the claim as unsupported, partially
    supported, ambiguous, or not verifiable as appropriate.
-   Do not automatically mark unresolved claims as verified.

------------------------------------------------------------------------

# 9. Shared LangGraph state

Use a typed state definition. Keep large document content in storage and
pass IDs/references through the graph where practical.

Required state fields:

  Field                    Purpose
  ------------------------ ---------------------------------------
  `document_id`            Workspace/document identifier
  `workflow_run_id`        Current workflow run
  `file_path`              Stored PDF path
  `document_metadata`      Extracted metadata
  `page_records`           Page text and page mapping references
  `sections`               Section hierarchy
  `chunk_ids`              Indexed chunk references
  `current_task`           Active extraction/query task
  `retrieval_results`      Retrieved evidence references
  `extracted_claims`       Claims produced by extraction
  `evidence_registry`      Evidence references
  `verification_results`   Claim verification results
  `retry_counts`           Retry count per task/claim
  `processing_status`      Current workflow status
  `processing_errors`      Errors and warnings
  `final_output_id`        Persisted result reference
  `conversation_id`        Chat context when applicable

Use LangGraph checkpointing for workflow recovery where supported. Keep
checkpoint storage and application persistence responsibilities clear;
do not duplicate the same data without a reason.

------------------------------------------------------------------------

# 10. Database design

Use SQLite with SQLAlchemy and Alembic.

Suggested tables:

## 10.1 `documents`

-   `id`
-   `original_filename`
-   `stored_filename`
-   `file_path`
-   `sha256`
-   `file_size`
-   `title`
-   `authors_json`
-   `publication_year`
-   `doi`
-   `status`
-   `created_at`
-   `updated_at`

## 10.2 `document_pages`

-   `id`
-   `document_id`
-   `pdf_page_index`
-   `displayed_page_number`
-   `page_text`
-   `ocr_used`
-   `extraction_status`

## 10.3 `extractions`

-   `id`
-   `document_id`
-   `schema_version`
-   `model_id`
-   `prompt_version`
-   `embedding_model_id`
-   `index_version`
-   `result_json`
-   `status`
-   `created_at`

## 10.4 `claims`

-   `id`
-   `extraction_id`
-   `claim_id`
-   `category`
-   `claim_text`
-   `origin`
-   `extraction_status`
-   `verification_status`
-   `confidence`
-   `verification_explanation`

## 10.5 `evidence`

-   `id`
-   `claim_id`
-   `evidence_id`
-   `pdf_page_index`
-   `displayed_page_number`
-   `section_name`
-   `source_text`
-   `verification_status`
-   `verification_explanation`

## 10.6 `conversations`

-   `id`
-   `document_id`
-   `created_at`
-   `updated_at`

## 10.7 `messages`

-   `id`
-   `conversation_id`
-   `role`
-   `content`
-   `citations_json`
-   `created_at`

## 10.8 `processing_runs`

-   `id`
-   `document_id`
-   `workflow_run_id`
-   `stage`
-   `status`
-   `started_at`
-   `completed_at`
-   `error_json`
-   `metrics_json`

Add appropriate foreign keys, indexes, uniqueness constraints, and
cascade/deletion behaviour. Use database migrations. Avoid storing
sensitive API credentials in the database.

## 10.9 ChromaDB

Use persistent ChromaDB storage. Isolate each document's chunks using a
document-specific collection or equivalent namespace. Metadata must
include:

-   `document_id`;
-   `chunk_id`;
-   `pdf_page_index`;
-   `displayed_page_number` when known;
-   `section_name`;
-   chunk text or retrievable text reference;
-   `index_version`.

When a document is deleted, remove its vector records and associated
application records.

------------------------------------------------------------------------

# 11. FastAPI endpoint specification

Use versioned routes under `/api`.

  ---------------------------------------------------------------------------------------------
  Method                  Endpoint                                      Purpose
  ----------------------- --------------------------------------------- -----------------------
  GET                     `/api/health`                                 Health check

  POST                    `/api/documents/upload`                       Upload and register PDF

  GET                     `/api/documents`                              List
                                                                        workspaces/documents

  GET                     `/api/documents/{document_id}`                Document details

  POST                    `/api/documents/{document_id}/analyze`        Start analysis

  GET                     `/api/documents/{document_id}/status`         Processing status

  GET                     `/api/documents/{document_id}/analysis`       Retrieve structured
                                                                        analysis

  GET                     `/api/documents/{document_id}/evidence`       Retrieve evidence

  POST                    `/api/documents/{document_id}/chat`           Ask a question

  GET                     `/api/documents/{document_id}/chat/history`   Conversation history

  POST                    `/api/documents/{document_id}/report`         Generate report

  GET                     `/api/reports/{report_id}`                    Download generated
                                                                        report

  DELETE                  `/api/documents/{document_id}`                Delete document and
                                                                        associated data
  ---------------------------------------------------------------------------------------------

Use Pydantic request/response models. Return meaningful HTTP status
codes and structured error responses.

Analysis is a long-running operation. The analyze endpoint should
enqueue/start a background job and return a run identifier promptly. The
frontend should poll the status endpoint or use a suitable progress
mechanism. For the first local prototype, a simple persistent
worker/background-job implementation is sufficient. Do not introduce
Redis, Celery, Kubernetes, or distributed services without a
demonstrated requirement.

------------------------------------------------------------------------

# 12. Frontend requirements

Use React, Vite, and Tailwind CSS.

## 12.1 Main pages

1.  Dashboard
2.  Upload Research Paper
3.  Processing Status
4.  Paper Overview
5.  Research Analysis
6.  Technical Analysis
7.  Evidence Verification
8.  Research Assistant
9.  Reports

## 12.2 Dashboard

Show:

-   welcome/overview;
-   upload action;
-   current or recent paper workspace;
-   processing status;
-   quick navigation to analysis, assistant, and reports.

## 12.3 Paper analysis interface

Organize information into readable sections/tabs:

-   Overview and metadata
-   Abstract
-   Research problem
-   Objectives
-   Motivation
-   Background
-   Methodology
-   Algorithms and models
-   Dataset and experiments
-   Results
-   Limitations
-   Future scope
-   Research contributions
-   Technical terminology

## 12.4 Evidence interface

For each claim, display:

-   claim text;
-   category;
-   verification status;
-   source page;
-   section;
-   supporting passage;
-   verification explanation.

Never use color as the only indication of status. Include text labels
and accessible visual cues.

## 12.5 Conversational interface

Display:

-   user and assistant messages;
-   citations linked to page references;
-   supporting passages;
-   clear insufficient-evidence responses;
-   conversation history within the workspace.

## 12.6 Processing interface

Show real workflow stages, such as:

1.  Upload validation
2.  Document extraction
3.  Section identification
4.  Retrieval indexing
5.  Knowledge extraction
6.  Evidence verification
7.  Saving analysis
8.  Analysis ready

Show partial completion and actionable errors rather than a generic
infinite loading indicator.

------------------------------------------------------------------------

# 13. Report generation

Support:

-   JSON export of the validated extraction;
-   PDF research analysis report;
-   DOCX research analysis report.

The report should contain:

1.  Paper metadata
2.  Abstract and overview
3.  Research problem
4.  Objectives and motivation
5.  Background
6.  Methodology
7.  Algorithms and models
8.  Dataset and experimental setup
9.  Results and findings
10. Research contributions
11. Limitations
12. Future scope
13. Technical methodology breakdown
14. Technical terminology
15. Verification summary
16. Evidence and page references

The report must distinguish source-derived claims from system-generated
explanations and inferences. Do not invent missing content to make the
report look complete.

------------------------------------------------------------------------

# 14. Error handling and reliability

Handle at least these cases:

  -----------------------------------------------------------------------
  Condition                           Expected behaviour
  ----------------------------------- -----------------------------------
  Invalid file type                   Reject with explanation

  File exceeds configured size        Reject with explanation

  Encrypted PDF                       Explain unsupported file

  Corrupt PDF                         Reject or report partial processing

  Scanned PDF                         Attempt OCR

  OCR failure                         Mark affected pages and analysis
                                      partial

  Missing metadata                    Mark `not_found`

  Missing extraction category         Continue other categories

  LLM timeout                         Bounded retry with backoff

  Provider rate limit                 Respect retry guidance and backoff

  Invalid structured output           Parse/validate, retry or report
                                      failure

  Unsupported claim                   Retain and mark unsupported

  Incorrect page mapping              Flag and prevent false citation

  Workflow interruption               Resume from checkpoint when
                                      possible

  Duplicate upload                    Detect SHA-256 and offer
                                      reuse/rejection

  Database error                      Log safely and return a useful
                                      error

  ChromaDB error                      Report indexing/retrieval failure;
                                      do not claim analysis is ready
  -----------------------------------------------------------------------

Distinguish these situations:

-   information is absent from the paper;
-   information may be present but retrieval failed;
-   information was extracted but evidence does not support it;
-   source text could not be processed reliably.

------------------------------------------------------------------------

# 15. Security and privacy

1.  Validate uploaded file content; do not trust filename extensions
    alone.
2.  Generate safe internal filenames.
3.  Store uploads in a controlled directory.
4.  Keep API keys in environment variables.
5.  Never expose API keys to React or browser code.
6.  Treat all PDF content as untrusted data.
7.  Protect against prompt injection embedded in documents.
8.  Treat document instructions as quoted source content, never as
    system/developer instructions.
9.  Do not execute embedded scripts, attachments, or active content from
    PDFs.
10. Restrict file access to the relevant workspace.
11. Delete document files, database records, vectors, and reports when a
    document is deleted, subject to clearly documented retention rules.
12. Avoid logging API keys, private document contents, or unnecessary
    personal data.
13. Use public research papers for initial development and test data.
14. Review current provider data-use terms before processing
    confidential or unpublished papers.

------------------------------------------------------------------------

# 16. Project folder structure

Use this as the intended modular structure. Create modules as their
phase requires them; do not create a large set of empty files
prematurely.

``` text
agentic-research-assistant/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── documents.py
│   │   │   ├── analysis.py
│   │   │   ├── chat.py
│   │   │   └── reports.py
│   │   ├── agents/
│   │   │   ├── coordinator.py
│   │   │   ├── extraction_agent.py
│   │   │   ├── verification_agent.py
│   │   │   └── research_assistant.py
│   │   ├── workflows/
│   │   │   ├── analysis_graph.py
│   │   │   ├── chat_graph.py
│   │   │   └── graph_state.py
│   │   ├── document_processing/
│   │   │   ├── pdf_parser.py
│   │   │   ├── ocr.py
│   │   │   ├── section_detector.py
│   │   │   └── chunker.py
│   │   ├── retrieval/
│   │   │   ├── embeddings.py
│   │   │   ├── vector_store.py
│   │   │   ├── keyword_search.py
│   │   │   └── hybrid_search.py
│   │   ├── schemas/
│   │   │   ├── paper.py
│   │   │   ├── extraction.py
│   │   │   ├── evidence.py
│   │   │   ├── verification.py
│   │   │   └── api.py
│   │   ├── database/
│   │   │   ├── models.py
│   │   │   ├── connection.py
│   │   │   └── repository.py
│   │   ├── services/
│   │   │   ├── llm_service.py
│   │   │   ├── document_service.py
│   │   │   ├── analysis_service.py
│   │   │   └── report_service.py
│   │   └── prompts/
│   │       ├── extraction.py
│   │       ├── verification.py
│   │       └── assistant.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── layouts/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── context/
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
│
├── storage/
│   ├── uploads/
│   ├── chroma/
│   ├── reports/
│   └── database/
│
├── evaluation/
│   ├── test_papers/
│   ├── ground_truth/
│   ├── retrieval_tests.py
│   ├── extraction_tests.py
│   └── verification_tests.py
│
├── docs/
│   ├── architecture.md
│   ├── extraction_schema.md
│   └── evaluation_methodology.md
│
├── DEVELOPMENT_LOG.md
├── README.md
├── .gitignore
└── PROJECT_CONTEXT.md
```

------------------------------------------------------------------------

# 17. Development roadmap

Estimated schedule: approximately 8 weeks. Adjust based on actual
progress, model/API access, PDF complexity, and testing results. The
schedule is an estimate, not a guarantee.

## Phase 1 --- Project foundation

Tasks: - initialize repository; - create Python virtual environment; -
set up FastAPI; - initialize React + Vite; - configure Tailwind; -
configure environment variables; - install compatible dependencies; -
initialize SQLite and ChromaDB; - implement health-check endpoint; -
establish logging and configuration.

Acceptance criteria: - backend starts; - frontend starts; - frontend can
reach backend; - database connection works; - secrets are not exposed in
frontend.

## Phase 2 --- PDF processing and indexing

Tasks: - PDF upload and validation; - SHA-256 duplicate detection; -
page-wise text extraction; - scanned-page detection; - OCR fallback; -
section identification; - metadata extraction; - section-aware
chunking; - embedding generation; - ChromaDB indexing; - BM25 indexing.

Acceptance criteria: - text-based academic PDF processes successfully; -
page mappings are preserved; - OCR is attempted on scanned pages; -
chunks are searchable; - indexing errors are reported accurately.

## Phase 3 --- LLM integration and structured extraction

Tasks: - configure Gemini SDK; - verify model access and supported API
method; - create reusable LLM service; - implement Pydantic schemas; -
implement structured output; - create category-specific prompts; -
extract all 12 categories; - implement four additional intelligence
capabilities; - attach claim/evidence references; - handle missing and
ambiguous fields.

Acceptance criteria: - output validates against Pydantic; - every
category has a defined status; - missing data is not fabricated; -
numerical results retain context; - claims reference evidence records.

## Phase 4 --- LangGraph orchestration

Tasks: - define shared state; - implement analysis workflow; - implement
extraction and verification nodes; - implement coordinator and
routing; - add retry limits; - add checkpointing; - add error and status
tracking.

Acceptance criteria: - workflow executes in controlled order; - state is
passed correctly; - conditional routing works; - retry limits are
enforced; - workflow ends in success, partial completion, or a
meaningful failure state.

## Phase 5 --- Evidence verification

Tasks: - claim-level verification; - source passage retrieval; - entity
and numerical checks; - evidence entailment assessment; -
unsupported/partial/contradicted classification; - citation mapping
checks; - verification explanations; - targeted retries.

Acceptance criteria: - unsupported claims are not marked verified; -
source text is inspected; - page references are checked; - verification
status is persisted; - unresolved claims remain visibly unresolved.

## Phase 6 --- Retrieval and research assistant

Tasks: - hybrid search; - RRF ranking; - section-aware filtering; -
optional reranker evaluation; - Q&A workflow; - conversation context; -
source-grounded answers; - citation validation; - insufficient-evidence
response.

Acceptance criteria: - questions retrieve relevant passages; - answers
cite source pages; - follow-up questions work; - unsupported answers are
not fabricated.

## Phase 7 --- Persistence and report generation

Tasks: - SQLAlchemy models; - Alembic migrations; - repositories; -
persist claims/evidence/results; - persist conversations; - deletion
workflow; - JSON export; - PDF and DOCX generation.

Acceptance criteria: - data survives application restart; -
relationships remain valid; - exports include source references; -
deletion removes associated records and vectors.

## Phase 8 --- Frontend development

Tasks: - dashboard; - PDF upload; - processing progress; - paper
overview; - extraction category views; - technical analysis; - evidence
verification; - conversational assistant; - report download.

Acceptance criteria: - complete user journey works; - processing state
is visible; - claims and evidence are inspectable; - chat and report
export work.

## Phase 9 --- Integration and NLP evaluation

Tasks: - unit and integration testing; - prepare manually annotated
papers; - evaluate retrieval; - evaluate extraction; - evaluate
verification; - evaluate citation accuracy; - measure processing time; -
compare semantic vs hybrid retrieval; - analyze failure cases.

Acceptance criteria: - results are reproducible; - metric calculations
are documented; - test sample sizes are reported; - failures and
limitations are disclosed.

## Phase 10 --- Finalization and demonstration

Tasks: - resolve critical bugs; - optimize performance; - verify fresh
installation; - finalize documentation; - prepare demo paper and
scenarios; - prepare architecture diagrams; - prepare final presentation
material.

Acceptance criteria: - application can be installed from documented
instructions; - a complete single-paper analysis can be demonstrated; -
outputs are inspectable and exportable; - known limitations are
documented.

------------------------------------------------------------------------

# 18. Testing and research evaluation

This is an NLP project, so the final demonstration must include
measurable evaluation rather than only screenshots or a successful
chatbot conversation.

## 18.1 Evaluation dataset

Begin with approximately 10--20 public academic research papers, subject
to time and annotation effort.

For each paper, manually annotate relevant fields from the extraction
schema. Record source passages and page references. Have a human review
the reference annotations.

Do not use model-generated outputs as ground truth without human review.

## 18.2 Retrieval metrics

Evaluate:

-   Precision@K;
-   Recall@K;
-   Mean Reciprocal Rank (MRR).

Compare semantic retrieval with hybrid retrieval using the same query
set and relevance labels.

## 18.3 Extraction metrics

For extractable facts/entities, evaluate:

-   precision;
-   recall;
-   F1-score.

Define the unit of evaluation for each category. For free-text
summaries, use a documented human assessment rubric rather than treating
a semantic similarity score as factual correctness.

## 18.4 Verification metrics

Create manually labelled claim/evidence pairs and evaluate:

-   accuracy;
-   precision and recall for supported/unsupported classes;
-   confusion matrix;
-   false acceptance rate (unsupported claims incorrectly marked
    verified);
-   false rejection rate (supported claims incorrectly rejected).

The false acceptance rate is especially important.

## 18.5 Citation evaluation

Measure:

-   correct source passage attribution;
-   correct PDF page index;
-   correct displayed page number where identifiable;
-   citation-to-claim support.

## 18.6 Performance evaluation

Record:

-   PDF page count;
-   file size;
-   processing duration;
-   extraction duration;
-   verification duration;
-   number of LLM calls;
-   token usage if available;
-   retry count;
-   indexing duration.

Do not report performance values until they have actually been measured.

## 18.7 Reproducibility

Record:

-   model ID;
-   SDK version;
-   prompt version;
-   schema version;
-   embedding model ID;
-   chunking configuration;
-   retrieval configuration;
-   test dataset version.

------------------------------------------------------------------------

# 19. Claude implementation rules and working protocol

Use the following workflow throughout implementation.

## Before each phase

1.  Read this specification and `DEVELOPMENT_LOG.md`.
2.  Inspect the repository.
3.  Identify the phase's dependencies.
4.  List files to create or modify.
5.  State the planned implementation and tests.
6.  Identify any missing prerequisites.

## During implementation

1.  Implement small, coherent components.
2.  Use typed Python interfaces.
3.  Add docstrings where they improve clarity.
4.  Keep prompts in dedicated modules.
5.  Keep configuration centralized.
6.  Use dependency injection for external services where practical.
7.  Add unit tests for business logic.
8.  Mock external API calls in routine tests.
9.  Do not make paid API calls during every unit test.
10. Log useful metadata without leaking secrets or document contents
    unnecessarily.

## At phase completion

1.  Run formatting/linting tools selected for the repository.
2.  Run relevant automated tests.
3.  Run an integration test where appropriate.
4.  Report exactly what passed and failed.
5.  Update `DEVELOPMENT_LOG.md`.
6.  List remaining limitations.
7.  Recommend the next phase only after acceptance criteria are met.

## If something fails

Do not hide failures with broad exception handlers or fake fallback
outputs. Return explicit errors, preserve diagnostic information, and
mark the analysis as failed or partially complete where appropriate.

## If a requirement appears ambiguous

Use the simplest interpretation consistent with this specification. If
the ambiguity would materially alter the architecture, stop and ask for
clarification rather than silently making a major change.

------------------------------------------------------------------------

# 20. Initial Claude task

Do not begin by implementing all ten phases.

Start with **Phase 1 only**.

First response expected from Claude:

1.  Summarize the project and its locked scope.
2.  Inspect the current repository (if one exists).
3.  Check the installed Python and Node versions.
4.  Check current official SDK/library compatibility for the chosen
    stack.
5.  Propose the Phase 1 file changes.
6.  Identify required environment variables.
7.  Implement the foundation.
8.  Run and report Phase 1 tests.
9.  Update `DEVELOPMENT_LOG.md`.

Do not start Phase 2 until Phase 1 acceptance criteria are satisfied.

------------------------------------------------------------------------

# 21. Known limitations and honest claims

The application is an assistant for analyzing one paper, not an
authority on scientific truth.

Known limitations to document and test:

-   PDF text extraction can fail on complex layouts.
-   OCR may introduce transcription errors.
-   Tables, equations, diagrams, and multi-column formatting may require
    special handling.
-   Section detection may be imperfect.
-   LLM extraction may omit or misinterpret content.
-   Verification can make mistakes and is not a formal proof of
    correctness.
-   Page numbering can differ between the PDF viewer and printed page
    labels.
-   Retrieval may fail to surface a relevant passage.
-   Author claims and system inferences can be difficult to distinguish.
-   Research reports may omit information not available in the source.
-   API availability, costs, rate limits, and model behaviour can
    change.

The UI and documentation must not claim that the system guarantees
hallucination-free output, perfect extraction, or scientific validation.

Use wording such as "evidence-supported," "verified against retrieved
source passages," and "verification status" rather than claiming
absolute truth.

------------------------------------------------------------------------

# 22. Official technical references

Use current official documentation during implementation. Documentation
and model availability can change.

-   Gemini API models: https://ai.google.dev/gemini-api/docs/models
-   Gemini structured outputs:
    https://ai.google.dev/gemini-api/docs/structured-output
-   Gemini API getting started:
    https://ai.google.dev/gemini-api/docs/get-started
-   LangGraph overview:
    https://docs.langchain.com/oss/python/langgraph/overview
-   LangGraph persistence:
    https://docs.langchain.com/oss/python/langgraph/persistence
-   Sentence Transformers: https://www.sbert.net/
-   Selected embedding model:
    https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1
-   Chroma documentation: https://docs.trychroma.com/
-   PyMuPDF documentation: https://pymupdf.readthedocs.io/
-   FastAPI documentation: https://fastapi.tiangolo.com/
-   Pydantic documentation: https://docs.pydantic.dev/
-   SQLAlchemy documentation: https://docs.sqlalchemy.org/
-   React documentation: https://react.dev/
-   Vite documentation: https://vite.dev/

------------------------------------------------------------------------

# 23. Final project principles

These principles take precedence over convenience during implementation.

1.  **Single-paper only:** Never combine different papers or workspaces.
2.  **Evidence first:** Every factual claim should be traceable to the
    source.
3.  **No fabrication:** Missing information must remain missing.
4.  **Separation of origin:** Author statements, extracted facts, and
    system inferences must be distinguishable.
5.  **Controlled agents:** Use LangGraph state and bounded routing, not
    unrestricted loops.
6.  **Validate outputs:** LLM-generated JSON must pass Pydantic and
    semantic checks.
7.  **Preserve provenance:** Keep page, section, passage, model, prompt,
    and schema references.
8.  **Build incrementally:** Complete and test one phase before moving
    forward.
9.  **Keep the stack lean:** Do not add Neo4j, another vector database,
    another LLM provider, or distributed infrastructure without a
    demonstrated need.
10. **Evaluate honestly:** Report measured results, sample sizes,
    limitations, and failures.
11. **Protect documents and credentials:** Treat uploads as untrusted
    and keep secrets server-side.
12. **Understandable implementation:** Keep the code modular and
    explainable so the student can understand and defend the project.

**End of master project specification.**

------------------------------------------------------------------------

# Amendment A1 — Reduced mini-project scope (approved 2026-11-05)

**Reason:** this is a college mini project and the deadline has effectively passed (about
one day left). The user approved a lighter scope and a lighter working process. This
amendment overrides the earlier sections where they conflict; everything not mentioned
here stays as specified. Phases 1–2 are complete and Phase 3 is implemented.

## A1.1 Working process (overrides §0 items 5–7 and §19 where heavier)

- Tests cover the important paths only; no exhaustive test suites.
- One quick self-review per step; no multi-agent reviews.
- `DEVELOPMENT_LOG.md` entries are short: what was done, test result, known limits.
- Known minor defects may be recorded as limitations instead of fixed, if they do not
  produce fabricated evidence or lose data.

## A1.2 Remaining roadmap (replaces §17 Phases 4–10)

| Step | Content | Reduced from |
|------|---------|--------------|
| 4. Orchestration | A minimal LangGraph graph wrapping the existing stages (process → index → extract → verify), with the existing bounded retries. No elaborate checkpointing. | Phase 4 |
| 5. Verification | Per claim: deterministic checks (quote located, numbers in claim appear in the quote) plus one LLM judgement of support → verified / partially_supported / unsupported / contradicted / not_verifiable. | Phase 5 |
| 6. Assistant + export | Q&A about the current paper using hybrid retrieval with RRF, page citations, insufficient-evidence answers, conversation history. Export: JSON and PDF. | Phases 6–7 |
| 7. Frontend | Four pages: upload + processing status, analysis view, evidence/verification view, assistant. | Phase 8 |
| 8. Evaluation + finish | 3–5 manually annotated public papers; retrieval (P@K, MRR), extraction spot-check, verification accuracy on labelled claims; sample sizes reported. Short README with install and demo steps. | Phases 9–10 |

## A1.3 Dropped or deferred (not required for completion)

- DOCX export (JSON and PDF remain).
- Relational `claims` / `evidence` tables (§10.4–10.5): the validated analysis is stored as
  JSON in `extractions.result_json`, which already holds claims and evidence with IDs.
- LangGraph checkpoint-based workflow recovery beyond the existing interrupted-run handling.
- Optional reranker evaluation; semantic-vs-hybrid comparison only if time allows.
- Separate Dashboard, Paper Overview, Technical Analysis and Reports pages (merged into the
  four pages above).
- Evaluation on 10–20 papers (reduced to 3–5).

Single-paper scope, evidence-first behaviour, no fabrication, separation of author and
system content, and honest reporting (§23) are unchanged.

------------------------------------------------------------------------

# Amendment A2 — LLM access through OpenRouter (approved 2026-11-05)

**Reason:** the user switched to an OpenRouter API key. The direct Gemini API free tier
allows only 20 requests per day per model and was returning 503 "high demand".

- **Model unchanged:** Gemini 3.8 Flash, reached as `google/gemini-3.8-flash` on OpenRouter.
- **Route:** OpenRouter's chat API with a strict JSON Schema (`response_format`
  `json_schema`, `provider.require_parameters`), replacing the Google GenAI SDK for this
  key. The Google SDK route stays available (`LLM_PROVIDER=gemini`).
- **Selection:** `LLM_PROVIDER=auto` (default) uses OpenRouter when the key starts with
  `sk-or-` (in `OPENROUTER_API_KEY` or `GEMINI_API_KEY`), otherwise the Google SDK.
- **Speed settings (also approved):** three merged extraction calls run in parallel;
  reasoning effort "low"; quota errors fail at once; at most one retry for server errors.
- Pricing and credit are the user's OpenRouter account; no costs are promised here.
