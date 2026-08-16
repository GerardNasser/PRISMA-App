# Field config spec

A field config declares everything the app needs to render the right forms,
defaults, and modules for a `(field, review_type)` pair: reporting
checklist, registries, databases, extraction template, risk-of-bias tool,
effect sizes, synthesis modules, publication-bias methods, and certainty
framework.

The canonical contract is `prismapi/fields/registry/_schema.json` (JSON
Schema Draft 2020-12). The YAML files in the same directory are validated
against it at startup — a malformed config stops the app with an error
naming the file.

## Naming

`id = "<field>__<review_type>"` (double underscore). The twelve configs
that ship today:

`health__intervention`, `health__observational`, `health__diagnostic`,
`health__omics`, `preclinical__animal`, `social__economics`,
`social__education`, `social__psychology`, `environmental__ecology`,
`engineering__slr`, `qualitative__synthesis`, `general__custom`.

## Versioning

Each config carries `version` (semver) and `effective_date`. Projects pin
the config version they were created with, so registry updates never change
an in-flight review. Any content change to a shipped config needs a version
bump.

## Required sections

Ten sections are mandatory: `reporting`, `registries`, `databases`,
`extraction_template`, `risk_of_bias`, `effect_sizes`, `synthesis`,
`publication_bias`, `certainty`, and `modules`. Optional: `branch_choices`
(up-front wizard questions), `qrp_warnings`, `citations`, `verify_flags`.

Two mechanics worth knowing:

- `branch_choices` renders as a wizard step; the project stores the chosen
  values.
- `risk_of_bias.tool_by_choice` maps one branch choice's values to RoB
  tools, so a config whose designs span randomised and non-randomised
  studies can hand RCTs to RoB 2 and quasi-experiments to ROBINS-I.
  Unmapped values fall back to the config's default `tool`.

## Adding a config

1. Consult the field's primary methodology sources — the `citations` lists
   in the shipped configs show the expected register.
2. Copy the closest existing YAML (`health__intervention` is the most
   complete exemplar).
3. Update `id`, `field`, `review_type`, `label`, `summary`, `version`,
   `effective_date`.
4. Fill in the ten required sections. Match tools to designs: RoB 2 for
   randomised trials, ROBINS-I for non-randomised interventions, ROBINS-E
   for observational exposures, QUADAS-2 for diagnostic accuracy, QUIPS for
   prognostic questions, SYRCLE for animal studies. Review-level appraisal
   tools (AMSTAR-2, ROBIS, CEESAT) rate whole reviews and never belong in
   `risk_of_bias`.
5. Check registry scope: PROSPERO only accepts reviews with a health-related
   outcome. Use OSF (or a field registry such as PROCEED for environmental
   evidence) elsewhere.
6. Add field-specific `qrp_warnings` and real, verifiable `citations`.
7. Validate:

   ```bash
   python -m prismapi.fields.validate
   ```

8. Add a test in `tests/test_fields_registry.py` asserting the config's
   distinctive settings.

## What configs must not do

- Embed primary-study data or project-level state.
- Hard-code journal-specific text — keep guidance generic per field.
- Cite sources that have not been checked. A wrong or misattributed
  citation in a config steers real reviews wrong.
