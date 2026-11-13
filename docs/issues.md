# Ontology Extraction Issues

## 1. Business classes are split into selectable profiles

The always-loaded `business.yaml` profile contains shared business classes.
Order-to-cash, procurement, fulfillment/logistics, revenue/accounting,
governance/risk/compliance, and products/inventory classes are in optional
business profiles. Every class remains declared in one of these profile files;
mentioning a name only in `type_sets`, relationship `domain`, or relationship
`range` does not make it an allowed node type.

## 2. Relationship endpoints depend on selected profiles

The YAML contains relationships such as:

```text
Sales Order -> has discount approval -> Discount Approval
Sales Order -> invoiced as -> Invoice
Sales Order -> shipped via -> Shipment
```

The relationship is available with its relevant optional profile. The adapter
resolves endpoint constraints against classes from the profiles selected for
the extraction, so endpoints belonging to unselected profiles are not allowed.

## 3. Limited extraction properties — fixed

The business YAML now defines structured property names for nodes and
relationships. The graph transformer receives these property names when
structured output is supported.

Node properties include:

- amount
- date
- status
- currency
- delivery duration
- priority

Relationship properties include:

- effective_date
- delivery_date
- status
- duration
- notes

The application still preserves source values as written; numeric/date
normalization can be added as a later post-processing step.

## 4. Extraction recall can still be incomplete

Even when a class and relationship are present in the YAML context, the LLM
may omit facts from the document. This is an extraction-recall issue rather
than a downstream validation issue.

Potential contributing factors include long YAML context, repeated or broad
relationship definitions, ambiguous document language, and the model deciding
that a fact is not sufficiently explicit.

## 5. Conflicting and ambiguous source facts — priority 98/100

The `o2c_test_3.1.pdf` run contains source statements that conflict or lack
enough detail to interpret reliably:

- ORD-1005 is reported as shipped on 2026-06-01 but delivered on 2026-05-20.
- ORD-1001 moves from `Delivered` to `Dispatched`, `On Hold`, and `In Production`
  without timestamps to establish the sequence.
- Charlotte is referred to as both a facility and a plant, while different
  orders name different fulfillment sites.

Resolve these conflicts in the source or explicitly label them as conflicting
records and include dates/times for status changes. Extraction should preserve
the conflicting source claims rather than infer a corrected timeline.

## 6. Missing evidence on extracted assertions — priority 95/100

The logged extraction produced 19 assertions, all marked with
`evidence_status: missing`, despite each being marked valid by the semantic and
SHACL checks. Validation therefore does not establish that assertions are
traceable to source evidence. Preserve the exact supporting text span and its
source document and chunk identifiers for each assertion, and report missing
evidence distinctly from ontology validity.

## 7. Oversized mixed-order chunks — priority 90/100

The logged input combines five separate orders in one 1,989-character chunk.
This makes it harder to associate each customer, product, site, status, and
action with the correct order. Prefer order-bounded chunks with a clear order
identifier, while repeating or linking only the shared context required for
interpretation. Keep cross-order facts explicit rather than relying on
proximity in a combined chunk.

## 8. Ambiguous people, roles, and actions — priority 85/100

The input sometimes names a job title without identifying its holder, and
sometimes uses a person's name and role inconsistently. The extraction
represented several people or titles with generic
`PARTICIPATES_IN_AT_SOME_TIME` relationships rather than capturing the
specific action. State each action as an explicit subject-verb-object fact and
distinguish the person from their role, for example:
`Dana Wells (person), acting as Customer Account Manager, approved the discount
for ORD-1001.` Where the role holder is unknown, say so instead of presenting
the role title as a person.

## 9. Inconsistent financial values and currency context — priority 80/100

For ORD-1001, the stated gross amount of USD 12,500 less a USD 1,000 discount
calculates to USD 11,500, not the stated net revenue of USD 11,000. For ORD-1002,
the order amount is stated in euros while invoicing is described as USD without
the invoice amount, exchange rate, or conversion date. Reconcile calculated
amounts at the source and label order, discount, net, and invoice amounts with
their currencies. Include the exchange rate and effective date when converting
currencies.

## 10. `o2c_test_3.1.pdf` extraction findings — priority 95/100

The run selected the order-to-cash, fulfillment/logistics, and
revenue/accounting profiles, which broadly match the document. The extraction
nevertheless produced only 19 assertions: 2 `HAS_CUSTOMER`, 3 `FULFILLED_FROM`,
3 `HAS_INPUT`, and 11 generic `PARTICIPATES_IN_AT_SOME_TIME` relationships.

Run-specific issues:

- **Important workflow facts were omitted — priority 95/100.** The output did
  not capture discount approvals, the credit check, invoice generation,
  revenue recognition, shipping method, status changes, or the ORD-1005
  shipment and delivery dates, although these are stated in the input and
  relevant concepts are available in the selected context.
- **Actions were reduced to generic participation — priority 90/100.** Dana
  Wells's discount approval and Priya Rao's credit validation were represented
  as participation in an order instead of preserving the actions performed.
- **Job titles were typed as people — priority 85/100.** Unnamed roles such as
  Sales Director, Revenue Accountant, Plant Production Coordinator, and
  Logistics & Shipping Manager were typed as `Person`; the source does not
  establish that these role titles identify individual people.
- **Assignment and shipping origin were conflated — priority 85/100.** ORD-1002
  is assigned to Charlotte Bromine Facility but is also said to have shipped
  from Houston Plant. The extraction records only `FULFILLED_FROM` Houston,
  without distinguishing the assigned facility from the shipping origin.
- **Status chronology is incomplete and ambiguous — priority 90/100.** The
  source gives ORD-1001 status changes without timestamps, and reports
  ORD-1005 as shipped after its delivery date. The extraction does not capture
  these status and date facts.
- **Financial values need source clarification — priority 80/100.** ORD-1001's
  gross and discount imply a different net amount than stated. ORD-1002's
  amount and invoice use different currencies without conversion details. The
  extractor should preserve supplied values, not guess a correction.
- **Assertions lack traceable evidence — priority 95/100.** All 19 assertions
  are marked `evidence_status: missing`; the source document ID is null and
  the evidence refers to `unknown-document`. Semantic validation was disabled.
  SHACL acceptance therefore does not demonstrate factual support or
  extraction fidelity.

Improve the source by separating orders into clearly identified sections,
resolving or explicitly marking conflicting facts, and stating actions with
their actor, role, action, and order. Independently address evidence capture
so assertions retain the source document and supporting chunk or text span.

## 11. `cabalmar_plant_fulfillment_process.pdf` extraction findings — priority 92/100

The run selected order-to-cash, fulfillment/logistics, production planning, and
manufacturing-system organization profiles. It produced 147 assertions, all
accepted by the logged SHACL check. Several entity and relationship assignments
still conflict with the selected ontology context or the source wording:

- **Plant hierarchy uses an incompatible relationship — priority 95/100.**
  `Cabalmar Chemicals —has sub-unit→ [Plant]` was extracted for the ten plants.
  The selected context defines `has sub-unit` with `Organizational Unit` as its
  range, while these targets are typed as `Plant`. Use a relationship whose
  range permits plants, or represent the plants through an appropriate
  organizational-unit structure.
- **`PERFORMED_BY` direction is reversed in some assertions — priority 90/100.**
  Examples include `Plant QA Lead —performed by→ Plant QA Lead Review` and
  `Warehouse & Dispatch Supervisor —performed by→ Order Picking`. The process
  should be the subject and the responsible person or role the object.
- **Job titles are inconsistently typed as people — priority 85/100.** The
  source's responsibilities table lists titles such as Plant Production
  Coordinator and Plant Manager, not named individuals. These are represented
  as `Employee Role` in some assertions and as `Person` in participation
  assertions. Keep the role distinct from any named person who holds it.
- **Statuses are modeled as entities of the wrong kind — priority 85/100.**
  `In Production Status` is typed as a `Production Order` and linked to
  `SAP Production Order` using `PARTICIPATES_IN_AT_SOME_TIME`. The source says
  the status is set on the SAP production order and reflected in the O2C
  system; represent it as a status value/property or an appropriate status
  relation, not another production order.
- **System interactions use participation relationships — priority 80/100.**
  The output links `Certificate Of Analysis` to `SAP QM` and `Finished Goods
  Warehouse` to `Warehouse Management System (WMS)` with
  `PARTICIPATES_IN_AT_SOME_TIME`. The source instead describes a certificate
  generated in SAP QM and warehouse/batch details recorded in WMS. Use
  relations that express generation, recording, or system association if
  available; otherwise avoid asserting a misleading participation edge.
- **The Certificate of Analysis appears with inconsistent entity types —
  priority 80/100.** It is extracted as both an `Information Content Entity`
  and a `Shipping Document`. These may refer to the same CoA; consolidate or
  distinguish them only if the source establishes separate records.
- **A position is used as the performer — priority 75/100.** The output links
  Plant Performance Reporting to `VP Operations` typed as a `Position` via
  `PERFORMED_BY`. The source identifies the document owner as VP of Plant
  Operations; that title alone does not establish a specific person or that a
  position entity is the performer.

These are extraction-quality issues despite SHACL acceptance. Add or tighten
semantic checks for relationship endpoint types and direction, and retain
source evidence for each assertion so incorrect interpretations can be
reviewed against the relevant text.
