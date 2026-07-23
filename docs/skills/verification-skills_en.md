# Verification Skill

The verification workflow is consolidated into one orchestrator skill: `.agents/skills/devops-verification/`. Its `SKILL.md` + `references/workflow.yaml` are the single source of truth for the pipeline; this doc is a guide and does not duplicate the skill (to avoid drift).

## One skill, six stages

The `devops-verification` skill runs a sequential pipeline (provider-aware via `git_provider.type`), stopping at the first `BLOCKED`:

1. `resource-readiness` — config + credentials check (before any refresh/query)
2. `workspace-alignment` — SLS project / logstore alignment (before refresh)
3. `workspace-refresh` — run the data ingestion (the central step; if skipped or written to the wrong project, downstream is meaningless)
4. `cms-visibility` — confirm `devops.*` entities are visible in CMS (after refresh)
5. `cms-field-check` — validate key fields per provider (after visibility passes)
6. `cms-sls-diagnose` — only when refresh/visibility are unexpected

Core principle: `workspace-refresh` writes data first — subsequent queries and checks are meaningless without it.

## Entry point and contracts

- Skill entry: `.agents/skills/devops-verification/SKILL.md`
- Machine-readable pipeline: `.agents/skills/devops-verification/references/workflow.yaml`
- Stage definitions / prerequisites / config contract / receipt schema / failure routing / script map: see the corresponding files under `references/`
- Scripts: `devops_data_generator/scripts/` (`query_cms_devops.py` / `verify_devops_details.py` / `diagnose_cms_entity_store.py`) + `devops_data_generator/main.py` (refresh)

## Receipt

Each stage emits a structured receipt (full schema in `.agents/skills/devops-verification/references/receipt-contract.md`). Example:

```
- stage: <stage-id>
- git_provider: gitlab | codeup   # derived from app_config.yaml, never hardcoded
- verdict: PASS | FAIL | BLOCKED
- [stage-specific fields]
```
