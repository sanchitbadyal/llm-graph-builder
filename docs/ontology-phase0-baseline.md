# Ontology-Guided Knowledge Graph — Phase 0 Baseline

Date: 2026-11-03

This document records the current architecture before ontology-guided extraction changes. It is a baseline only; it does not change runtime behavior.

## Scope and working-tree safety

The repository already contains modified and untracked user work. Phase 0 preserves those changes and does not reset, delete, or rewrite existing files.

## Current execution flow

```text
Document source
  -> source loader
  -> document chunking
  -> Chunk nodes and embeddings in Neo4j
  -> LLM provider selection
  -> LangChain LLMGraphTransformer / Diffbot transformer
  -> GraphDocument output
  -> node canonicalization and duplicate merging
  -> entity and relationship validation
  -> Cabalmar business-rule validation
  -> Neo4j entity/relationship persistence
  -> vector/full-text/community retrieval
  -> GraphRAG chat and business queries
```

Primary implementation locations:

- `backend/src/main.py` — ingestion and processing orchestration.
- `backend/src/llm.py` — LLM selection and graph transformation.
- `backend/src/create_chunks.py` — document chunking.
- `backend/src/graphDB_dataAccess.py` — Neo4j persistence, embeddings, and indexes.
- `backend/src/validation/` — deterministic validation.
- `backend/src/QA_integration.py` — retrieval and GraphRAG chat.

## Current runtime authority

The application runtime is YAML-driven. `backend/src/business_model.py` loads:

```text
backend/src/business_model/BusinessModel.yaml
```

The YAML profile currently supplies:

| Item | Count |
|---|---:|
| Entity types | 35 |
| Relationship definitions | 53 |
| Business-rule categories | 16 |
| Business rules | 84 |
| Taxonomy sections | 15 |

The OWL files are not currently loaded by the extraction or validation runtime.

## Ontology artifact inventory

| File | Intended layer | Classes | Object properties | Imports |
|---|---|---:|---:|---:|
| `backend/src/Ontology/foundational ontology.rdf` | BFO foundation | 20 | 40 | 0 |
| `backend/src/Ontology/business.owl` | Business ontology | 34 | 12 | BFO |
| `backend/src/Ontology/cabalmar-domain.owl` | Cabalmar domain | 35 | 51 | Business |

Current intended dependency graph:

```text
foundational ontology.rdf
        ^
        |
business.owl
        ^
        |
cabalmar-domain.owl
```

Current import and publication limitations:

- `business.owl` imports the external BFO IRI rather than a local catalog-managed artifact.
- `cabalmar-domain.owl` imports the Business ontology using an `example.org` namespace.
- Business and Cabalmar namespaces are placeholders and are not production identifiers.
- There is no ontology manifest, version pinning, checksum record, or local import catalog.
- There is no runtime OWL import resolver or semantic closure service.

## Current extraction contract

The LLM extraction path uses:

- provider-specific LangChain chat models;
- `LLMGraphTransformer` or Diffbot graph transformation;
- allowed node labels;
- allowed relationship triples;
- additional instructions generated from `BusinessModel.yaml`;
- optional node and relationship descriptions.

The current contract is label-oriented. It does not require the LLM result to contain:

- canonical ontology class IRIs;
- canonical property IRIs;
- ontology layer;
- explicit versus inferred assertion status;
- exact evidence spans;
- deterministic validation status.

## Current graph and provenance contract

Neo4j stores operational graph data, including source documents, chunks, entities, relationships, embeddings, and communities. Chunk IDs and source metadata are available to the pipeline.

The current contract does not yet guarantee first-class assertion provenance containing all of:

- source document identifier and version;
- page number;
- chunk identifier;
- character offsets;
- exact supporting text span;
- assertion status;
- validation result;
- ontology IRIs.

## Current validation layers

Existing deterministic validation includes:

1. Entity type and property validation.
2. Relationship signature and endpoint validation.
3. Duplicate/canonicalization handling.
4. Cabalmar business-rule validation.

The repository does not yet execute:

- OWL consistency validation;
- imported ontology closure validation;
- SHACL validation;
- ontology-aware entity resolution;
- evidence-span verification.

## Target compatibility boundary

The proposed architecture should preserve the following boundaries:

```text
OWL/RDF
  = canonical class/property identity and stable semantic meaning

YAML or rule engine
  = extraction configuration, source mappings, conflicts, KPIs,
    volatile operational rules, and application settings

Neo4j
  = operational graph projection, retrieval, GraphRAG, and evidence access
```

The first ontology-guided implementation should wrap the existing LLM Graph Builder rather than replace it:

```text
OWL/RDF artifacts
  -> ontology resolver
  -> compact extraction context
  -> existing LLMGraphTransformer
  -> structured ontology-aware extraction envelope
  -> OWL/SHACL/evidence validation
  -> existing Neo4j persistence
```

## Baseline risks

- Duplicate semantic definitions may diverge between OWL and `BusinessModel.yaml`.
- Placeholder namespaces cannot be treated as production identity.
- External ontology imports are not currently reproducibly resolved.
- Neo4j labels and IDs are not yet guaranteed to preserve OWL IRIs.
- LLM confidence must not be treated as factual verification.
- Existing graph queries may depend on current labels and relationship names.
- Adding ontology validation synchronously may increase ingestion latency.

## Test baseline

The repository contains tests under `tests/` and a root `pytest.ini`. `pytest` is installed in the project virtual environment (`pytest 9.2.0`), but the complete suite is not currently executable because the environment is missing application dependencies.

Observed commands and blockers:

```text
venv/bin/python -m pytest -q
  collection fails in backend/Performance_test.py: missing requests

PYTHONPATH=backend VALIDATOR_MODULE=src.validation.business_rule_validator \
  venv/bin/python -m pytest tests -q
  collection fails in tests/business_rules/test_business_rules.py: missing yaml/PyYAML
```

The test suite therefore remains an open Phase 0 item. Installing the complete application dependency set should be treated as a separate environment/bootstrap action, not silently performed as part of ontology changes.

## Phase 0 exit criteria

- [x] Current execution flow documented.
- [x] Neo4j and LLM Graph Builder integration points documented.
- [x] OWL/RDF artifact inventory recorded.
- [x] Current YAML runtime authority recorded.
- [x] Current validation layers recorded.
- [x] Provenance limitations recorded.
- [x] Compatibility risks recorded.
- [ ] Test suite executed successfully in the project environment; currently blocked by missing `requests` and `PyYAML` dependencies.
- [ ] Ontology import/version manifest approved.
- [ ] Canonical production namespaces approved.

## Implementation update — 2026-11-03

The Phase 0 document above is retained as a historical baseline. The ontology
layer has since been implemented as an additive runtime path.

### Current runtime modes

The application now supports two modes:

```text
Legacy compatibility mode
  BusinessModel.yaml -> existing extraction/business-rule validation

Ontology-only mode
  OWL manifest/import closure
    -> semantic context
    -> existing LLMGraphTransformer
    -> extraction envelope
    -> semantic validation
    -> SHACL validation
    -> entity resolution
    -> evidence verification
    -> Neo4j projection
```

Ontology-only mode is enabled with:

```text
ONTOLOGY_ONLY_MODE=true
ONTOLOGY_GUIDED_EXTRACTION=true
```

The YAML files remain in the repository for compatibility, but they are not
required by the ontology-only extraction path. Existing Neo4j labels and
relationship types remain unchanged.

### Implemented ontology capabilities

- Manifest artifact metadata, checksums, versions, and local paths.
- RDF/XML import validation and root-first import closure.
- Semantic indexing of classes, properties, labels, ancestors, domains, ranges,
  inverse properties, and ontology layers.
- Ontology-generated LLM allowlists and prompt context.
- Structured extraction assertions and envelopes.
- Evidence provenance fields and chunk/span/hash verification.
- Deterministic class/property/domain/range validation.
- Initial SHACL validation using `rdflib` and `pyshacl`.
- Conservative Neo4j-backed entity resolution with ambiguity quarantine.
- Additive Neo4j entity and relationship ontology/provenance metadata.
- Ontology-aware query planning and answer-policy context.
- OWL/YAML authority policy, drift reports, version checks, and non-destructive
  IRI migration plans.

### Current limitations

- The LLMGraphTransformer does not yet reliably emit exact evidence spans;
  strict evidence enforcement is therefore opt-in with
  `ONTOLOGY_REQUIRE_EXACT_EVIDENCE=true`.
- SHACL currently contains a base assertion/evidence shape, not the full set of
  domain-specific shapes.
- Entity resolution uses deterministic aliases and Neo4j metadata; vector
  candidate retrieval and automatic duplicate merging are not enabled.
- Existing Neo4j data is not automatically migrated when ontology IRIs change.
- Full OWL DL consistency/reasoner validation is not yet part of ingestion.
- The generated query plan is supplied to GraphRAG answer context; direct
  application of every ontology filter inside every vector retrieval query is
  still pending.

### Updated phase status

```text
Phase 0  baseline/documentation                  complete
Phase 1  manifest/artifact model                 complete
Phase 2  import resolution/semantic loading      complete
Phase 3  YAML-to-OWL generation                  re-scoped; OWL is authored and loaded directly
Phase 4  semantic resolver                       complete
Phase 5  ontology context generation             complete
Phase 6  structured extraction envelope          implemented with span limitation
Phase 7  deterministic semantic validation        complete for current graph model
Phase 8  SHACL                                    initial shapes implemented
Phase 9  entity resolution                        deterministic/Neo4j path implemented
Phase 10 evidence verification                    implemented; strict span emission pending
Phase 11 Neo4j ontology projection               implemented additively
Phase 12 ontology-aware GraphRAG                 query planning implemented; direct filter pending
Phase 13 OWL/YAML authority boundary             compatibility and migration tooling implemented
```

## Implementation update — 2026-11-04

The company-specific YAML business-model implementation has now been removed
from the runtime and repository:

- `backend/src/business_model.py` was removed.
- `backend/src/business_model/*.yaml` was removed.
- YAML business-rule, entity, relationship, and profile validators were removed.
- YAML business-rule and entity-validation tests were removed.
- `PyYAML` was removed from `backend/requirements.txt`.

Extraction constraints now come from the OWL ontology profile. The LLM receives
the human-readable ontology context, while structured transformer constraints
remain separately enforced:

```text
Human-readable ontology context
  -> LLM comprehension

allowed_nodes / allowed_relationships
  -> LLMGraphTransformer constraints

SemanticResolver
  -> deterministic post-extraction validation
```

The raw JSON ontology context remains available for diagnostics and future
machine processing, but it is not the primary ontology prompt text.

Ontology extraction events are persisted in a readable log at:

```text
backend/logs/ontology-extraction.log
```

The log records raw and accepted envelope stages, source names, validation
reports, evidence status, assertion IDs, IRIs, and provenance.

The current generic runtime is now:

```text
OWL manifest/import closure
  -> human-readable ontology context
  -> structured transformer allowlists
  -> LLMGraphTransformer
  -> extraction envelope
  -> semantic validation
  -> SHACL validation
  -> entity resolution
  -> evidence verification
  -> Neo4j ontology/provenance projection
  -> ontology-aware GraphRAG
```

The legacy Cabalmar YAML validation path is no longer available. Company-
specific operational rules must be implemented as optional deployment profile
validators or SHACL shapes rather than restored as a core YAML dependency.

