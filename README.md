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
     │  ├─ 13 tasks          │
     │  ├─ SLS sender        │
     │  └─ orchestrator      │
     └──────────┬───────────┘
                │ SLS / CMS write
                ▼
     ┌──────────────────────┐
     │  UModel Explorer     │
     │  5 EntitySet          │
     │  12 EntitySetLink     │
     └──────────────────────┘
```

## Quick Start

### GitLab

```bash
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
# Edit app_config.yaml — fill in url, access_token, project_id, SLS/ACR/CMS credentials

docker compose up --build
```

### Codeup

```bash
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
# Edit app_config.yaml — fill in organization_id, access_key, SLS/ACR/CMS credentials

docker compose -f docker-compose.codeup.yml up --build
```

Switch providers by changing `git_provider.type` in `app_config.yaml` — no code changes required.

## UModel Schema

| Domain | EntitySet | Description |
|---|---|---|
| devops | `devops.developer` | Developer / team member |
| devops | `devops.code_repository` | Git repository |
| devops | `devops.code_release` | Release / tag |
| devops | `devops.image_registry` | Container image registry (ACR) |
| devops | `devops.image` | Container image |

12 EntitySetLinks connect these entities and bridge to `apm.service` and `k8s.{pod,deployment,daemonset,statefulset}`.

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

```bash
python3 umodel_uploader/umodel_batch_uploader.py umodel \
  --endpoint metrics.<REGION>.aliyuncs.com \
  --workspace <YOUR_WORKSPACE>
```

## Project Structure

```
umodel-devops-reference/
├── umodel/                          # 5 EntitySet + 12 EntitySetLink
├── umodel_uploader/                 # Batch upload tool
├── devops_data_generator/
│   ├── adapters/{gitlab,codeup}/    # IGitAdapter implementations
│   ├── tasks/                       # 13 data ingestion tasks
│   ├── config/                      # Sample configs per provider
│   ├── orchestrator.py              # Task scheduling + structured results
│   └── scripts/                     # Verification + deployment scripts
├── .claude/skills/                  # 6 Claude verification skills
├── .codex/skills/                   # 6 Codex verification skills
├── shared/verification/             # Verification contracts
├── docker-compose.yml               # GitLab mode
├── docker-compose.codeup.yml        # Codeup mode
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
