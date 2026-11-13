# Ontology YAML Profiles

The YAML files in `backend/src/Ontology/profiles/` provide curated ontology
context for graph extraction. Each profile declares classes (with labels,
definitions, and parent classes) and relationships (with labels, domains, and
ranges). The `type_sets` in some files are reusable groups of relationship
endpoints; they are not additional classes.

The counts below refer to class and relationship entries declared in each
profile's YAML. A particular extraction uses the profiles selected for that
run, rather than necessarily using every profile.

## Business profiles

`business.yaml` is the always-loaded **Business Common** profile. It provides
shared organizations, organizational units, roles, positions, locations, and
general business relationships. It declares 11 classes and 20 relationships.
The following business profiles are optional and selected according to the
document:

| Profile file | Focus | Classes | Relationships |
|---|---|---:|---:|
| `business_order_to_cash.yaml` | Customer sales, orders, contracts, credit checks, discounts, billing, and invoices | 16 | 8 |
| `business_procurement_supplier_management.yaml` | Purchase orders and requisitions, receiving, procurement, and suppliers | 4 | 4 |
| `business_fulfillment_logistics.yaml` | Fulfillment, shipments, delivery, transfers, plants, and shipping documents | 11 | 10 |
| `business_revenue_accounting.yaml` | Accounts, accounting entries, revenue recognition, accruals, and periods | 10 | 5 |
| `business_governance_risk_compliance.yaml` | Policies, rules, risks, controls, approvals, assessments, and compliance | 10 | 12 |
| `business_products_inventory.yaml` | Products, product categories, specifications, manufacturing, and inventory | 5 | 4 |

Across Business Common and all six optional profiles, the original 67 business
classes and 63 relationships are each declared once. Domain-specific profile
selection limits which specialized vocabulary is sent to the extractor.

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

`core.yaml` and Business Common are always loaded. The six optional business
profiles add commercial and operational detail as needed. `production.yaml`,
`maintenance.yaml`, and `certification.yaml` add focused domain vocabulary,
while `manufacturing_system_organiztion.yaml` describes the structure and
resources of a manufacturing environment. Profiles can refer to foundational
classes from one another; the selected profiles determine which specialized
domain vocabulary is available as extraction context for a run.
