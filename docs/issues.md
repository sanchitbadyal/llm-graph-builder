# Ontology Extraction Issues

## 1. Missing O2C entity classes

Several entities referenced by the business relationships are not defined as
classes under `business.yaml -> groups`.

Examples:

- Sales Order
- Customer
- Plant
- Manufactured Product
- Carrier
- Profit Center
- Proof Of Delivery
- Sales Contract

Mentioning these names in `type_sets`, relationship `domain`, or relationship
`range` does not make them allowed node types. They must be declared as class
entries under `groups`.

## 2. No dedicated O2C or revenue profile selector option

The profile selector currently offers only these optional profiles:

- `production-planning-complete`
- `maintenance-complete`
- `certification-complete`
- `manufacturing-system-organization-complete`

There is no separate selector option for order-to-cash, plant fulfillment, or
revenue recognition. Their concepts are intended to be included in the
always-loaded business profile.

## 3. Relationship vocabulary is broader than the class vocabulary

The YAML contains relationships such as:

```text
Sales Order -> has discount approval -> Discount Approval
Sales Order -> invoiced as -> Invoice
Sales Order -> shipped via -> Shipment
```

But `Sales Order` is not currently declared as a class in the business profile.
This creates relationships whose endpoints are referenced but not fully
defined in the active class vocabulary.

## 4. Limited extraction properties — fixed

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

## 5. Extraction recall can still be incomplete

Even when a class and relationship are present in the YAML context, the LLM
may omit facts from the document. This is an extraction-recall issue rather
than a downstream validation issue.

Potential contributing factors include long YAML context, repeated or broad
relationship definitions, ambiguous document language, and the model deciding
that a fact is not sufficiently explicit.
