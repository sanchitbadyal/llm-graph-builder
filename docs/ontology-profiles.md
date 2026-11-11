# Ontology YAML Profiles

The YAML files in `backend/src/Ontology/profiles/` provide curated ontology
context for graph extraction. Each profile declares classes (with labels,
definitions, and parent classes) and relationships (with labels, domains, and
ranges). The `type_sets` in some files are reusable groups of relationship
endpoints; they are not additional classes.

The counts below refer to class and relationship entries declared in each
profile's YAML. A particular extraction uses the profiles selected for that
run, rather than necessarily using every profile.

## `business.yaml`

**Role:** Business operations, organizational structure, and commercial
transactions.

Its classes cover:

- Organizations, organizational units, locations, warehouses, and business
  roles.
- Business documents and transactions, including sales and purchase orders,
  contracts, quotes, and receipts.
- Order fulfillment, manufacturing in a business context, shipping, delivery,
  and inventory transfers.
- Invoicing, payments, accounting, revenue recognition, and financial periods.
- Approvals, credit checks, discount approvals, policies, risks, and controls.

Representative classes include `Sales Order`, `Customer`, `Plant`, `Shipment`,
`Invoice`, `Revenue Recognition`, `Credit Check`, and `Discount Approval`.
The profile declares 67 classes and 56 relationships, connecting parties,
documents, locations, fulfillment, approvals, and accounting concepts.

## `core.yaml`

**Role:** Foundational concepts reused by more specialized profiles.

Its classes cover agents and people, groups and roles, physical or material
things, equipment, processes, plans, information entities, capabilities, and
measurements.

Representative classes include `Agent`, `Person`, `Material Artifact`,
`Piece Of Equipment`, `Planned Process`, `Business Process`,
`Plan Specification`, and `Capability`. The profile declares 25 classes and
13 general relationships, including `has input`, `has output`, and `has role`.

## `production.yaml`

**Role:** Production planning and manufacturing execution.

Its classes cover production plans and orders, manufacturing operations and
process steps, machines and tools, operator roles, product specifications,
inspection, changeovers, and work-in-progress movement.

Representative classes include `Production Order`, `Production Plan`,
`Process Plan`, `Production Machine`, `Operator`, `Product Inspection Process`,
and `Work-In-Progress Transfer Process`. The profile declares 22 classes and
3 relationships about capabilities: `capability of`, `enabled by`, and
`enables`.

## `maintenance.yaml`

**Role:** Equipment condition, failures, and maintenance work.

Its classes cover failures and their effects, undesirable dispositions,
operating/degraded/failed states, required functions, maintenance strategies
and activities, work-order records, and qualified maintenance personnel.

Representative classes include `Failure Event`, `Failure Process`,
`Failure Effect`, `Operating State`, `Failed State`, `Maintenance Activity`,
`Maintenance Work Order Record`, and `Qualified Maintenance Person`. The
profile declares 20 classes and 3 relationships connecting maintainable items
to maintenance states and maintenance events to one another.

## `certification.yaml`

**Role:** Verification against requirements and formal certification.

Its classes cover attesting agents and roles, attestation and certificate
granting processes, certificates, and certifying organizations.

Representative classes include `Attesting Process`, `Attestation Certificate`,
`Certificate Granting Process`, and `Certifying Body`. The profile declares
7 classes and 4 relationships describing what a certificate attests to or
certifies, who grants it, and which entity has it.

## `manufacturing_system_organiztion.yaml`

**Role:** The physical and operational organization of a manufacturing system.
The filename spelling is retained as it exists in the repository.

Its classes cover enterprises, physical sites and areas, work centers and
work units, production lines and cells, storage zones and units, and equipment
or control modules.

Representative classes include `Enterprise`, `Physical Site`,
`Physical Area`, `Work Center`, `Production Line`, `Work Cell`, `Storage Zone`,
and `Control Module`. The profile declares 14 classes and 7 relationships
about aggregate membership, carrying processes, material basis, and
prescription by plans or specifications.

## How the profiles fit together

`core.yaml` provides broad building blocks. `business.yaml` describes
organizational and commercial workflows. `production.yaml`,
`maintenance.yaml`, and `certification.yaml` add focused domain vocabulary,
while `manufacturing_system_organiztion.yaml` describes the structure and
resources of a manufacturing environment. These profiles can refer to
foundational classes from one another; the selected profiles determine which
domain vocabulary is available as extraction context for a run.
