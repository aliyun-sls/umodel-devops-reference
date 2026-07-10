# umodel-devops-reference

面向 GitLab 和 Codeup（阿里云云效）的 UModel DevOps 接入参考实现。

将开发者、代码仓库、发布版本、容器镜像及拓扑关系从 Git 平台采集到 [UModel](https://help.aliyun.com/zh/cms/) 实体中，通过修改一个配置字段即可切换 Git 平台。

[English](README.md)

## 架构

```
┌─────────────┐     ┌─────────────┐
│   GitLab    │     │   Codeup    │
│（自建/SaaS） │     │（阿里云 SaaS）│
└──────┬──────┘     └──────┬──────┘
       │ python-gitlab      │ alibabacloud SDK
       └────────┬───────────┘
                │ IGitAdapter
                ▼
     ┌──────────────────────┐
     │  devops_data_generator│
      │  ├─ 15 个采集任务      │
      │  ├─ SLS 数据发送       │
      │  └─ 编排调度器         │
      └──────────┬───────────┘
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

## UModel 实体

17 个 EntitySet 覆盖完整研发链路（组织→项目→代码→CI/CD→发布→部署）。有 producer 支撑的实体（git + ACR 派生）：`devops.user`、`devops.repository`、`devops.release`、`devops.pull_request`、`devops.artifact`、`devops.docker_image`。其余 11 个（organization、project、work_item、milestone、pipeline、pipeline_run、helm_chart、binary、npm_package、unit_testcase、deployment）为 schema-only，待对应数据源 adapter（Jira/CI/appstack/制品库/组织系统）落地，详见 `docs/umodel-entity-field-contract.md`。

| 域 | 实体 | 有 producer |
|---|---|---|
| devops | `devops.user` | ✓（git） |
| devops | `devops.repository` | ✓（git） |
| devops | `devops.release` | ✓（git） |
| devops | `devops.pull_request` | ✓（git） |
| devops | `devops.artifact` | ✓（派生，ACR） |
| devops | `devops.docker_image` | ✓（ACR） |
| devops | + 11 个 schema-only | 待 adapter |

36 条 EntitySetLink 连接上述实体（29 条设计文档关系 + 跨域链接到 `apm.service` 和 `k8s.{pod,deployment,daemonset,statefulset}`）。

## 验证

6 个验证 Skill 覆盖完整链路，按 `git_provider.type` 智能判断检查项：

1. `verification-resource-readiness` — 配置与凭据检查
2. `verification-workspace-alignment` — SLS project / logstore 对齐
3. `verification-workspace-refresh` — 执行数据采集
4. `verification-cms-visibility` — 确认实体在 CMS 可见
5. `verification-cms-field-check` — 按平台验证字段值
6. `verification-cms-sls-diagnose` — 仅失败时进入

入口：`.claude/skills/<name>/SKILL.md` 和 `.codex/skills/<name>/SKILL.md`。

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
│   ├── adapters/{gitlab,codeup}/    # IGitAdapter 实现
│   ├── tasks/                       # 15 个数据采集任务
│   ├── config/                      # 各平台配置样例
│   ├── orchestrator.py              # 任务调度 + 结构化结果
│   └── scripts/                     # 验证 + 部署脚本
├── tools/                           # gen_umodel_yaml.py（schema 生成器）
├── .claude/skills/                  # 6 个 Claude 验证 Skill
├── .codex/skills/                   # 6 个 Codex 验证 Skill
├── shared/verification/             # 验证契约
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
