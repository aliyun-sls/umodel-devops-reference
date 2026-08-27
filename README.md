# umodel-devops-reference

UModel DevOps reference implementation for GitLab and Codeup (Alibaba Cloud DevOps).

Ingest developer, repository, release, image, and topology data from your git provider into [UModel](https://www.alibabacloud.com/help/en/cms/) entities — switch providers by changing one config field.

[中文文档](README_zh.md)

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   GitLab    │     │   Codeup    │     │   Argo CD   │
│  (self/SaaS)│     │ (China SaaS)│     │ (GitOps CD) │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │ python-gitlab      │ alibabacloud SDK │ REST API
       └────────┬───────────┘                  │
                │ IGitAdapter                  │ IDeployAdapter
                ▼                              ▼
      ┌──────────────────────────────────────────┐
      │  devops_data_generator                   │
      │  ├─ 21 tasks                             │
      │  ├─ SLS sender                           │
      │  └─ orchestrator                         │
      └──────────┬───────────────────────────────┘
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

### Entry Points

The generator ships two entry points — pick the one that matches your run model:

- **`main.py`** (CLI, the default in `docker-compose.yml`): runs a single cycle
  (`--mode single`) or continuous scheduled loops (`--mode continuous --interval`). No HTTP
  listener — this is what `docker compose up` runs.
- **`app.py`** (Flask HTTP API, the Dockerfile default `CMD`): exposes `POST /invoke`,
  `GET /status`, `GET /health`, `POST /stop` on port 5000 for externally-triggered runs.

Both share the same orchestrator and config; select by entry point rather than reimplementing
scheduling.

### Argo CD (optional CD source)

Add an `argocd` section to `app_config.yaml` (see the commented block in
`app_config.gitlab.yaml.sample`), then enable the two CD tasks:

```yaml
argocd:
  server: "https://<argocd-server>"     # API base URL, no trailing slash
  token: "<bearer token>"               # session/account token
  insecure: true                        # skip TLS verify (self-signed certs)
  app_filter: []                        # optional allowlist of application names
  repo_mapping:                         # repoURL → git repository_id
    "https://<git-host>/group/app.git": "1"

tasks:
  enabled:
    - deployment                        # devops.deployment entities
    - release_relates_to_deployment     # release → deployment edges
```

The CD tasks are provider-independent: they layer on top of either git provider's
run. Without an `argocd` section the producer behaves exactly as before.

## UModel Schema

17 EntitySets span the full DevOps lifecycle (org → project → code → CI/CD → release → deployment).
Producer-backed entities (git + GitLab CI + ACR + Argo CD derived): `devops.user`, `devops.repository`,
`devops.release`, `devops.pull_request`, `devops.artifact`, `devops.docker_image`,
`devops.deployment`, `devops.pipeline`, `devops.pipeline_run`, `devops.pipeline`, `devops.pipeline_run`. The remaining 8
(organization, project, work_item, milestone, helm_chart, binary,
npm_package, unit_testcase) are schema-only pending their data-source adapters
(Jira/CI/appstack/artifact-registry/org) — see `docs/umodel-entity-field-contract.md`.

| Domain | EntitySet | Producer-backed |
|---|---|---|
| devops | `devops.user` | ✓ (git) |
| devops | `devops.repository` | ✓ (git) |
| devops | `devops.release` | ✓ (git) |
| devops | `devops.pull_request` | ✓ (git) |
| devops | `devops.artifact` | ✓ (derived, ACR) |
| devops | `devops.docker_image` | ✓ (ACR) |
| devops | `devops.deployment` | ✓ (Argo CD) |
| devops | `devops.pipeline` | ✓ (GitLab CI / Jenkins) |
| devops | `devops.pipeline_run` | ✓ (GitLab CI / Jenkins) |
| devops | + 8 schema-only | pending adapters |

36 EntitySetLinks connect these entities (29 design-doc relations + cross-domain links to
`apm.service` and `k8s.{pod,deployment,daemonset,statefulset}`).

## Verification

The `devops-verification` skill is one orchestrator that runs a provider-aware 6-stage pipeline:

1. `verification-resource-readiness` — config and credentials check
2. `verification-workspace-alignment` — SLS project / logstore alignment
3. `verification-workspace-refresh` — run the data ingestion cycle
4. `verification-cms-visibility` — confirm entities appear in CMS
5. `verification-cms-field-check` — validate field values per provider
6. `verification-cms-sls-diagnose` — failure-only diagnostics

Entry point: `.agents/skills/devops-verification/SKILL.md` (pipeline flow in `references/workflow.yaml`).

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
│   ├── adapters/{gitlab,codeup,argocd}/ # IGitAdapter + IDeployAdapter implementations
│   ├── tasks/                       # 17 data ingestion tasks
│   ├── config/                      # Sample configs per provider
│   ├── orchestrator.py              # Task scheduling + structured results
│   └── scripts/                     # Verification + deployment scripts
├── tools/                           # gen_umodel_yaml.py (schema generator)
├── .agents/skills/                  # devops-verification skill (orchestrator + references)
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
