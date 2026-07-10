# umodel-devops-reference

UModel DevOps reference implementation for GitLab and Codeup (Alibaba Cloud DevOps).

Ingest developer, repository, release, image, and topology data from your git provider into [UModel](https://www.alibabacloud.com/help/en/cms/) entities — switch providers by changing one config field.

[中文文档](README_zh.md)

## Architecture

```
┌─────────────┐     ┌─────────────┐
│   GitLab    │     │   Codeup    │
│  (self/SaaS)│     │ (China SaaS)│
└──────┬──────┘     └──────┬──────┘
       │ python-gitlab      │ alibabacloud SDK
       └────────┬───────────┘
                │ IGitAdapter
                ▼
      ┌──────────────────────┐
      │  devops_data_generator│
      │  ├─ 15 tasks          │
      │  ├─ SLS sender        │
      │  └─ orchestrator      │
      └──────────┬───────────┘
                 │ SLS / CMS write
                 ▼
      ┌──────────────────────┐
      │  UModel Explorer     │
      │  17 EntitySet         │
      │  36 EntitySetLink     │
      └──────────────────────┘
```

## Quick Start

### GitLab

```bash
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
# Edit app_config.yaml — fill in url, access_token, project_id, SLS/ACR/CMS credentials
# Create .env for the schema uploader (this file is gitignored):
# ALIBABA_CLOUD_ACCESS_KEY_ID=<your-access-key-id>
# ALIBABA_CLOUD_ACCESS_KEY_SECRET=<your-access-key-secret>
# UMODEL_ENDPOINT=metrics.<REGION>.aliyuncs.com
# UMODEL_WORKSPACE=<your-workspace>

docker compose up --build
```

### Codeup

```bash
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
# Edit app_config.yaml — fill in organization_id, access_key, SLS/ACR/CMS credentials
# Create .env for the schema uploader as shown above.

docker compose up --build
```

The producer is selected by `git_provider.type` in `app_config.yaml`. The same Compose run also
starts the one-shot `umodel-schema-uploader`, which idempotently upserts the 17 EntitySets and
36 EntitySetLinks before exiting.

## UModel Schema

17 EntitySets span the full DevOps lifecycle (org → project → code → CI/CD → release → deployment).
Producer-backed entities (git + ACR derived): `devops.user`, `devops.repository`, `devops.release`,
`devops.pull_request`, `devops.artifact`, `devops.docker_image`. The remaining 11
(organization, project, work_item, milestone, pipeline, pipeline_run, helm_chart, binary,
npm_package, unit_testcase, deployment) are schema-only pending their data-source adapters
(Jira/CI/appstack/artifact-registry/org) — see `docs/umodel-entity-field-contract.md`.

| Domain | EntitySet | Producer-backed |
|---|---|---|
| devops | `devops.user` | ✓ (git) |
| devops | `devops.repository` | ✓ (git) |
| devops | `devops.release` | ✓ (git) |
| devops | `devops.pull_request` | ✓ (git) |
| devops | `devops.artifact` | ✓ (derived, ACR) |
| devops | `devops.docker_image` | ✓ (ACR) |
| devops | + 11 schema-only | pending adapters |

36 EntitySetLinks connect these entities (29 design-doc relations + cross-domain links to
`apm.service` and `k8s.{pod,deployment,daemonset,statefulset}`).

## Verification

Six provider-aware verification skills validate the full pipeline:

1. `verification-resource-readiness` — config and credentials check
2. `verification-workspace-alignment` — SLS project / logstore alignment
3. `verification-workspace-refresh` — run the data ingestion cycle
4. `verification-cms-visibility` — confirm entities appear in CMS
5. `verification-cms-field-check` — validate field values per provider
6. `verification-cms-sls-diagnose` — failure-only diagnostics

Entry points: `.claude/skills/<name>/SKILL.md` and `.codex/skills/<name>/SKILL.md`.

## Upload UModel Definitions

Compose runs the schema uploader automatically. Run it independently when validating or repairing
schema registration:

```bash
docker compose run --rm umodel-schema-uploader
```

The direct uploader command remains available for manual troubleshooting:

```bash
python3 umodel_uploader/umodel_batch_uploader.py umodel \
  --endpoint metrics.<REGION>.aliyuncs.com \
  --workspace <YOUR_WORKSPACE>
```

## Project Structure

```
umodel-devops-reference/
├── umodel/                          # 17 EntitySet + 36 EntitySetLink
├── umodel_uploader/                 # Batch upload tool
├── devops_data_generator/
│   ├── adapters/{gitlab,codeup}/    # IGitAdapter implementations
│   ├── tasks/                       # 15 data ingestion tasks
│   ├── config/                      # Sample configs per provider
│   ├── orchestrator.py              # Task scheduling + structured results
│   └── scripts/                     # Verification + deployment scripts
├── tools/                           # gen_umodel_yaml.py (schema generator)
├── .claude/skills/                  # 6 Claude verification skills
├── .codex/skills/                   # 6 Codex verification skills
├── shared/verification/             # Verification contracts
├── docker-compose.yml               # Data generator (provider selected by config)
└── docs/                            # Design + deployment + provider guides
```

## Documentation

- [Provider Matrix](docs/provider-matrix.md) | [中文](docs/provider-matrix_zh.md)
- [UModel Design](docs/aliyun/devops-enriched-umodel-design.md) | [English Summary](docs/aliyun/devops-enriched-umodel-design_en.md)
- [Deployment Guide](docs/aliyun/devops-process-enriched-deployment-guide.md) | [English Summary](docs/aliyun/devops-process-enriched-deployment-guide_en.md)
- [Implementation Guide](docs/aliyun/devops-process-enrichment-development-implementation-guide.md) | [English Summary](docs/aliyun/devops-process-enrichment-development-implementation-guide_en.md)
- [Scenario Overview](docs/aliyun/microservice-scenario-devops-process-enrichment-overview.md) | [English Summary](docs/aliyun/microservice-scenario-devops-process-enrichment-overview_en.md)
- [Verification Skills](docs/skills/verification-skills.md) | [English](docs/skills/verification-skills_en.md)

## License

Internal use.
