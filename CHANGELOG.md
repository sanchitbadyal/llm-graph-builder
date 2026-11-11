# Changelog

## Validator improvements

- Added structured Pydantic schema parsing for allowed nodes and relationships.
- Added case-insensitive duplicate merging, duplicate-edge detection, and duplicate property conflict reporting.
- Added rejection details, quarantine status, and validation counts to the taxonomy audit log.
- Added typed extraction for monetary values, percentages, currency, priority, status, and approved plant aliases.
- Added deterministic O2C checks for discount authorization, revenue arithmetic, required customer/plant links, and invalid taxonomy values.
- Added `drop_failed=False` to optionally remove quarantined graph items; the default preserves them with `validation_status=failed`.
- Ambiguous or unsupported business rules remain reported rather than inferred or silently enforced.

## Validator follow-up

- Fixed canonical CFO and credit/collections role resolution and promoted the remaining duplicate/date and unlabeled-discount regressions to normal tests.
- Added cross-node order context checks for plant mapping, invoice generator, revenue-recognition standard, freight, currency, and date rules.
- Added unlabeled discount parsing and explicit missing-field reporting.
- Added ambiguous-date handling so equivalent dates do not create duplicate conflicts and ambiguous dates do not create false conflicts.
- The current test suite completes with no failures, XPASS, or XFAIL results.
