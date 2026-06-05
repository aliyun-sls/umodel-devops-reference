# umodel-devops-reference

阿里云 STAROps「代码静态资源 ↔ UModel」DevOps 接入参考实现。把
GitLab 和 Codeup（云效）两条 git provider 路径融合到同一个 schema +
同一套抽象 adapter + 同一套 verification skill 下，由 `git_provider.type`
配置切换。

> 来源：融合自 `umodel-gitlab-devops-demo`（GitLab adapter + verification
> skill + 4 篇官方设计文档 + docker-compose）与 `umodel_and_codes.zip`
> （2025/10/21 阿里云官方发布的 Codeup adapter）。两套 adapter 拆到
> `devops_data_generator/adapters/{gitlab,codeup}/`，task 层通过
> `IGitAdapter` 接口调用，配置切换即可换 provider。

## 仓库定位

- **代码静态资源 ↔ UModel 的 demo 环境搭建**——客户拿一台机器、一份配置，
  能跑通从 git provider 抓数据 → 写入 SLS / CMS workspace → UModel
  Explorer 可见的完整链路。
- **不是**整套 DevOps 富化平台、不是生产级运维系统、不涉及 K8s runtime 资源
  细节（如 yunxiao.change_order ↔ k8s.configmap/ingress/pvc/service 的部署单
  挂载关系）。

## 目录结构

```
umodel-devops-reference/
├── umodel/                          # UModel schema (5 EntitySet + 12 EntitySetLink)
│   ├── entity_set/
│   └── entity_set_link/
├── umodel_uploader/                 # 批量上传 UModel 定义到 UModel Explorer
├── devops_data_generator/           # 数据接入引擎
│   ├── adapters/
│   │   ├── base.py                  # IGitAdapter ABC
│   │   ├── factory.py               # create_git_adapter(type, config)
│   │   ├── gitlab/                  # GitLabAdapter
│   │   └── codeup/                  # CodeupAdapter
│   ├── tasks/                       # 13 task (3 个 git task 通过 adapter 调用)
│   │   └── utils/release_classifier.py  # tag → release_type 共享分类器
│   ├── config/
│   │   ├── app_config.gitlab.yaml.sample
│   │   ├── app_config.codeup.yaml.sample
│   │   ├── data_mapping.yaml
│   │   ├── manage_mapping.yaml
│   │   ├── repo_image_mapping.yaml
│   │   └── static_topo.yaml
│   ├── orchestrator.py              # 多 provider + critical-task gating + structured result
│   ├── sender / generator / shared
│   ├── scripts/                     # 4 个 verification + docker / quick-start 脚本
│   └── Dockerfile + main.py + requirements.txt
├── .claude/skills/                  # 6 Claude verification skill
├── .codex/skills/                   # 6 Codex verification skill (双套)
├── shared/verification/             # verification 共享真相层 (config-contract / prerequisites / 等)
├── adapters/jenkins/                # 占位说明 v0.1 未新增
├── docker-compose.yml               # GitLab 模式 (启动 GitLab CE + data-generator)
├── docker-compose.codeup.yml        # Codeup 模式 (SaaS，仅启动 data-generator)
└── docs/
    ├── aliyun/                      # 4 篇官方设计文档
    ├── provider-matrix.md           # 何时用 codeup / 何时用 gitlab + 切换说明
    └── skills/                      # verification skill 使用说明
```

## Quick Start

### GitLab provider 路径

```bash
# 复制 sample 配置，填入 PAT / project_id 等
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml

# 启 GitLab CE + data-generator
docker compose -f docker-compose.yml up --build
```

### Codeup provider 路径

```bash
# 复制 sample 配置，填入 organization_id / aliyun ak/sk
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml

# 仅起 data-generator（codeup 是 SaaS）
docker compose -f docker-compose.codeup.yml up --build
```

切 provider **只需要换配置文件**，代码层无任何改动。详见
`docs/provider-matrix.md`。

## Verification

按固定 skill 顺序自检，覆盖两条 provider 路径：

1. `verification-resource-readiness`
2. `verification-workspace-alignment`
3. `verification-workspace-refresh`
4. `verification-cms-visibility`
5. `verification-cms-field-check`
6. `verification-cms-sls-diagnose`（仅失败时进入）

每个 skill 入口在 `.claude/skills/<name>/SKILL.md` / `.codex/skills/<name>/SKILL.md`，
共享真相层在 `shared/verification/`。

## 上传 UModel 定义

```bash
python3 umodel_uploader/umodel_batch_uploader.py umodel \
  --endpoint metrics.<REGION>.aliyuncs.com \
  --workspace <YOUR_WORKSPACE>
```

## v0.1 已知限制

- Codeup 端到端真实跑通延后到 v0.2（需 ak/sk + organization）。
- `python-gitlab` 和 `alibabacloud-devops20210625` v0.1 同时安装；v0.2 再
  拆 extras_require。
- 单元测试 / contract test 未引入；v0.1 接受标准 = 双 provider docker-compose
  端到端跑通。
- Jenkins / GitHub Actions / Argo / Tekton 不在 v0.1 范围。

详见 `docs/provider-matrix.md` § v0.1 已知限制。

## 关键设计文档

- `docs/aliyun/devops-enriched-umodel-design.md` —— UModel 设计
- `docs/aliyun/devops-process-enriched-deployment-guide.md` —— 部署指南
- `docs/aliyun/devops-process-enrichment-development-implementation-guide.md` —— 实现指南
- `docs/aliyun/microservice-scenario-devops-process-enrichment-overview.md` —— 场景总览
- `docs/provider-matrix.md` —— provider 矩阵 + 切换 + 已知限制
