# umodel-devops-reference

UModel DevOps reference implementation for GitLab and Codeup (Alibaba Cloud DevOps).

Ingest developer, repository, release, image, and topology data from your git provider into [UModel](https://www.alibabacloud.com/help/en/cms/) entities — switch providers by changing one config field.

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

Switch providers by changing `git_provider.type` in `app_config.yaml` — no code changes required. See [Provider Matrix](docs/provider-matrix.md) for details.

## UModel Schema

| Domain | EntitySet | Description |
|---|---|---|
| devops | `devops.developer` | Developer / team member |
| devops | `devops.code_repository` | Git repository |
| devops | `devops.code_release` | Release / tag |
| devops | `devops.image_registry` | Container image registry (ACR) |
| devops | `devops.image` | Container image |

12 EntitySetLinks connect these entities to each other and bridge to `apm.service` and `k8s.{pod,deployment,daemonset,statefulset}`.

## Verification

Six verification skills validate the full pipeline:

1. `verification-resource-readiness` — config and credentials check
2. `verification-workspace-alignment` — SLS project / logstore alignment
3. `verification-workspace-refresh` — run the data ingestion cycle
4. `verification-cms-visibility` — confirm entities appear in CMS
5. `verification-cms-field-check` — validate field values per provider
6. `verification-cms-sls-diagnose` — failure-only diagnostics

Skills are provider-aware: they read `git_provider.type` and assert the correct field values (`gitlab` vs `aliyun`).

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
├── umodel/                          # 5 EntitySet + 12 EntitySetLink definitions
├── umodel_uploader/                 # Batch upload tool
├── devops_data_generator/
│   ├── adapters/                    # IGitAdapter abstraction
│   │   ├── gitlab/                  # GitLab implementation
│   │   └── codeup/                  # Codeup implementation
│   ├── tasks/                       # 13 data ingestion tasks
│   ├── config/                      # Sample configs for each provider
│   ├── orchestrator.py              # Task scheduling + structured results
│   ├── sender/                      # SLS data sender
│   └── scripts/                     # Verification + deployment scripts
├── .claude/skills/                  # 6 Claude verification skills
├── .codex/skills/                   # 6 Codex verification skills
├── shared/verification/             # Verification contracts and prerequisites
├── docker-compose.yml               # GitLab mode (starts GitLab CE container)
├── docker-compose.codeup.yml        # Codeup mode (data-generator only)
└── docs/
    ├── aliyun/                      # UModel design + deployment guides
    └── provider-matrix.md           # Provider comparison and switching guide
```

## Documentation

- [Provider Matrix](docs/provider-matrix.md) — provider comparison, switching guide, field alignment
- [UModel Design](docs/aliyun/devops-enriched-umodel-design.md)
- [Deployment Guide](docs/aliyun/devops-process-enriched-deployment-guide.md)
- [Implementation Guide](docs/aliyun/devops-process-enrichment-development-implementation-guide.md)
- [Scenario Overview](docs/aliyun/microservice-scenario-devops-process-enrichment-overview.md)

## License

Internal use.

---

# umodel-devops-reference（中文）

面向 GitLab 和 Codeup（阿里云云效）的 UModel DevOps 接入参考实现。

将开发者、代码仓库、发布版本、容器镜像及拓扑关系从 Git 平台采集到 [UModel](https://help.aliyun.com/zh/cms/) 实体中，通过修改一个配置字段即可切换 Git 平台。

## 快速开始

### GitLab

```bash
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
# 编辑 app_config.yaml，填入 url、access_token、project_id、SLS/ACR/CMS 凭据

docker compose up --build
```

### Codeup

```bash
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
# 编辑 app_config.yaml，填入 organization_id、access_key、SLS/ACR/CMS 凭据

docker compose -f docker-compose.codeup.yml up --build
```

切换平台只需修改 `app_config.yaml` 中的 `git_provider.type`，无需改动代码。详见 [Provider Matrix](docs/provider-matrix.md)。

## UModel 实体

| 域 | 实体 | 说明 |
|---|---|---|
| devops | `devops.developer` | 开发者 |
| devops | `devops.code_repository` | 代码仓库 |
| devops | `devops.code_release` | 发布版本 / Tag |
| devops | `devops.image_registry` | 容器镜像仓库（ACR）|
| devops | `devops.image` | 容器镜像 |

12 条 EntitySetLink 连接上述实体，并桥接 `apm.service` 和 `k8s.{pod,deployment,daemonset,statefulset}`。

## 验证

6 个验证 Skill 覆盖完整链路，按 `git_provider.type` 智能判断检查项：

1. `verification-resource-readiness` — 配置与凭据检查
2. `verification-workspace-alignment` — SLS project / logstore 对齐
3. `verification-workspace-refresh` — 执行数据采集
4. `verification-cms-visibility` — 确认实体在 CMS 可见
5. `verification-cms-field-check` — 按平台验证字段值
6. `verification-cms-sls-diagnose` — 仅失败时进入

## 文档

- [Provider Matrix](docs/provider-matrix.md) — 平台对比、切换指南、字段对齐
- [UModel 设计文档](docs/aliyun/devops-enriched-umodel-design.md)
- [部署指南](docs/aliyun/devops-process-enriched-deployment-guide.md)
- [实现指南](docs/aliyun/devops-process-enrichment-development-implementation-guide.md)
- [场景总览](docs/aliyun/microservice-scenario-devops-process-enrichment-overview.md)
