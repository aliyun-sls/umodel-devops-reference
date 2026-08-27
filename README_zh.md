# umodel-devops-reference

面向 GitLab 和 Codeup（阿里云云效）的 UModel DevOps 接入参考实现。

将开发者、代码仓库、发布版本、容器镜像及拓扑关系从 Git 平台采集到 [UModel](https://help.aliyun.com/zh/cms/) 实体中，通过修改一个配置字段即可切换 Git 平台。

[English](README.md)

## 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   GitLab    │     │   Codeup    │     │   Argo CD   │
│（自建/SaaS） │     │（阿里云 SaaS）│     │(GitOps CD)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │ python-gitlab      │ alibabacloud SDK │ REST API
       └────────┬───────────┘                  │
                │ IGitAdapter                  │ IDeployAdapter
                ▼                              ▼
     ┌───────────────────────────────────────────┐
     │  devops_data_generator                    │
      │  ├─ 21 个采集任务                          │
      │  ├─ SLS 数据发送                           │
      │  └─ 编排调度器                              │
      └──────────┬────────────────────────────────┘
                 │ SLS / CMS 写入
                 ▼
      ┌──────────────────────┐
      │  UModel Explorer     │
      │  17 个 EntitySet      │
      │  36 条 EntitySetLink  │
      └──────────────────────┘
```

## 快速开始

### GitLab

```bash
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
# 编辑 app_config.yaml，填入 url、access_token、project_id、SLS/ACR/CMS 凭据
# 创建供 schema uploader 使用的 .env（该文件已被 gitignore）：
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
# 编辑 app_config.yaml，填入 organization_id、access_key、SLS/ACR/CMS 凭据
# 按上方说明创建供 schema uploader 使用的 .env。

docker compose up --build
```

producer 由 `app_config.yaml` 中的 `git_provider.type` 选择。同一次 Compose 启动还会运行一次性
`umodel-schema-uploader`，幂等 upsert 17 个 EntitySet 和 36 条 EntitySetLink 后退出。

### 入口

本生成器提供两个入口，按运行方式选用：

- **`main.py`**（CLI，`docker-compose.yml` 的默认入口）：运行单次周期（`--mode single`）或
  持续调度循环（`--mode continuous --interval`）。无 HTTP 监听——`docker compose up` 运行的即是它。
- **`app.py`**（Flask HTTP API，Dockerfile 的默认 `CMD`）：在 5000 端口暴露 `POST /invoke`、
  `GET /status`、`GET /health`、`POST /stop`，适用于外部触发式运行。

两者共用同一 orchestrator 与配置；按入口选用即可，无需另行实现调度。

### Argo CD（可选 CD 数据源）

在 `app_config.yaml` 里加 `argocd` 段（`app_config.gitlab.yaml.sample` 里有注释好的样例），
然后启用两个 CD 任务：

```yaml
argocd:
  server: "https://<argocd-server>"     # API 地址，结尾不带斜杠
  token: "<bearer token>"               # session/账号 token
  insecure: true                        # 跳过 TLS 校验（自签证书场景）
  app_filter: []                        # 可选：Application 白名单
  repo_mapping:                         # repoURL → git 仓库 repository_id
    "https://<git-host>/group/app.git": "1"

tasks:
  enabled:
    - deployment                        # devops.deployment 实体
    - release_relates_to_deployment     # release → deployment 边
```

CD 任务与 git provider 无关，可叠加在任一 provider 之上；不配 `argocd` 段时行为与之前完全一致。

## UModel 实体

17 个 EntitySet 覆盖完整研发链路（组织→项目→代码→CI/CD→发布→部署）。有 producer 支撑的实体（git + GitLab CI + ACR + Argo CD 派生）：`devops.user`、`devops.repository`、`devops.release`、`devops.pull_request`、`devops.artifact`、`devops.docker_image`、`devops.deployment`、`devops.pipeline`、`devops.pipeline_run`。其余 8 个（organization、project、work_item、milestone、helm_chart、binary、npm_package、unit_testcase）为 schema-only，待对应数据源 adapter（Jira/CI/appstack/制品库/组织系统）落地，详见 `docs/umodel-entity-field-contract.md`。

| 域 | 实体 | 有 producer |
|---|---|---|
| devops | `devops.user` | ✓（git） |
| devops | `devops.repository` | ✓（git） |
| devops | `devops.release` | ✓（git） |
| devops | `devops.pull_request` | ✓（git） |
| devops | `devops.artifact` | ✓（派生，ACR） |
| devops | `devops.docker_image` | ✓（ACR） |
| devops | `devops.deployment` | ✓（Argo CD） |
| devops | `devops.pipeline` | ✓（GitLab CI） |
| devops | `devops.pipeline_run` | ✓（GitLab CI） |
| devops | + 8 个 schema-only | 待 adapter |

36 条 EntitySetLink 连接上述实体（29 条设计文档关系 + 跨域链接到 `apm.service` 和 `k8s.{pod,deployment,daemonset,statefulset}`）。

## 验证

`devops-verification` skill 是单个 orchestrator，跑按 `git_provider.type` 智能判断的 6 阶段流水线：

1. `verification-resource-readiness` — 配置与凭据检查
2. `verification-workspace-alignment` — SLS project / logstore 对齐
3. `verification-workspace-refresh` — 执行数据采集
4. `verification-cms-visibility` — 确认实体在 CMS 可见
5. `verification-cms-field-check` — 按平台验证字段值
6. `verification-cms-sls-diagnose` — 仅失败时进入

入口：`.agents/skills/devops-verification/SKILL.md`（流水线在 `references/workflow.yaml`）。

## 上传 UModel 定义

Compose 会自动运行 schema uploader。需要单独验证或修复 schema 注册时，执行：

```bash
docker compose run --rm umodel-schema-uploader
```

以下直接调用 uploader 的方式保留作手动排障入口：

```bash
python3 umodel_uploader/umodel_batch_uploader.py umodel \
  --endpoint metrics.<REGION>.aliyuncs.com \
  --workspace <YOUR_WORKSPACE>
```

## 目录结构

```
umodel-devops-reference/
├── umodel/                          # 17 EntitySet + 36 EntitySetLink 定义
├── umodel_uploader/                 # 批量上传工具
├── devops_data_generator/
│   ├── adapters/{gitlab,codeup,argocd}/ # IGitAdapter + IDeployAdapter 实现
│   ├── tasks/                       # 17 个数据采集任务
│   ├── config/                      # 各平台配置样例
│   ├── orchestrator.py              # 任务调度 + 结构化结果
│   └── scripts/                     # 验证 + 部署脚本
├── tools/                           # gen_umodel_yaml.py（schema 生成器）
├── .agents/skills/                  # devops-verification skill（orchestrator + references）
├── docker-compose.yml               # 数据采集容器（平台由配置决定）
└── docs/                            # 设计 + 部署 + 平台指南
```

## 文档

- [Provider Matrix 中文](docs/provider-matrix_zh.md) | [English](docs/provider-matrix.md)
- [UModel 设计文档](docs/aliyun/devops-enriched-umodel-design.md)
- [部署指南](docs/aliyun/devops-process-enriched-deployment-guide.md)
- [实现指南](docs/aliyun/devops-process-enrichment-development-implementation-guide.md)
- [场景总览](docs/aliyun/microservice-scenario-devops-process-enrichment-overview.md)
- [验证 Skill 使用说明](docs/skills/verification-skills.md) | [English](docs/skills/verification-skills_en.md)

## License

Internal use.
