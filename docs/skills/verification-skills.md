# Verification Skill

验证工作流已合并为单个 orchestrator skill：`.agents/skills/devops-verification/`。其 `SKILL.md` + `references/workflow.yaml` 是流水线的唯一真相源；本文档为导览，不重复 skill 内容（避免漂移）。

## 单 skill、6 阶段

`devops-verification` skill 跑一条串行流水线（按 `git_provider.type` 智能判断检查项），遇 `BLOCKED` 即停：

1. `resource-readiness` — 配置与凭据检查（任何 refresh/query 之前）
2. `workspace-alignment` — SLS project / logstore 对齐（refresh 之前）
3. `workspace-refresh` — 执行数据采集（链路中心；没跑或写错 project，下游无意义）
4. `cms-visibility` — 确认 `devops.*` 实体在 CMS 可见（refresh 之后）
5. `cms-field-check` — 按平台验证关键字段（visibility 通过之后）
6. `cms-sls-diagnose` — 仅 refresh/visibility 异常时进入

核心原则：`workspace-refresh` 先把数据写进去，后面的查询与验证才有意义。

## 入口与契约

- Skill 入口：`.agents/skills/devops-verification/SKILL.md`
- 流水线机器定义：`.agents/skills/devops-verification/references/workflow.yaml`
- 阶段定义 / 前置条件 / 配置契约 / receipt schema / 失败路由 / 脚本映射：见 `references/` 下对应文件
- 执行脚本：`devops_data_generator/scripts/`（`query_cms_devops.py` / `verify_devops_details.py` / `diagnose_cms_entity_store.py`）+ `devops_data_generator/main.py`（refresh）

## Receipt

每个阶段输出结构化 receipt（完整 schema 见 `.agents/skills/devops-verification/references/receipt-contract.md`）。样例：

```
- stage: <stage-id>
- git_provider: gitlab | codeup   # 读自 app_config.yaml，不硬编码
- verdict: PASS | FAIL | BLOCKED
- [阶段专属字段]
```
