# Seeding the drift watch

From the repository root, run `python3 skills/listing-kit/scripts/specs/drift.py update --fetch`
once to seed this directory with digests of the upstream pages. Review and commit
the JSON files. Until then, the weekly check reports each missing baseline.
The small pages in `tests/fixtures/drift/` are synthetic test inputs.
