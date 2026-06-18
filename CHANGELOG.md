# Changelog

All notable changes to this repository. Dates are YYYY-MM-DD.

## [Unreleased] — UModel 全量实体对齐（破坏性重命名）

> 权威源：`docs/DevOps UModel设计-new.md`（17 实体 + 29 关系）。
> 对齐 spec：`docs/umodel-alignment-spec.md`（决策 A–G 已确认）。
> 字段契约 SSOT：`docs/umodel-entity-field-contract.md`。
> 本变更**破坏现有已入库数据**（见风险 R2），升级前需重建 workspace 或数据迁移。

### 破坏性重命名映射表

| 旧实体 | 新实体 | PK 迁移 |
|---|---|---|
| `devops.developer` | `devops.user` | `work_no` → `user_id` |
| `devops.code_repository` | `devops.repository` | `repo_id` → `repository_id` |
| `devops.code_release` | `devops.release` | `release_id`（保持） |
| `devops.image` | `devops.docker_image` | `image_id` → `docker_image_id` |
| `devops.image_registry` | **（移除，决策 A）** | registry 级属性折叠进 docker_image |

字段变更：`git_provider` 字段全局删除，统一为 `data_source`；codeup 值 `aliyun` → `codeup`。
关系命名词汇：仓库现 12 条关系全部重做，采用设计文档原生动词（决策 G-2）。
方向反转：`code_release_sourced_from_code_repository`（release→repo）→ `repository_tags_release`（repo→release）。

### 关键决策

- **决策 A**：移除 `image_registry` 实体 + `image_registry_contains_image` + `developer_manages_image_registry`。
- **决策 B**：ACR producer 一次 fetch 同生 `artifact` + `docker_image` + `artifact_same_as_docker_image`。
- **决策 C**：跨域关系保留；k8s 链接目标 `image`→`docker_image`；apm 源实体 `developer`→`user`。
- **决策 D**：删 `git_provider`，统一 `data_source`；codeup `aliyun`→`codeup`。
- **决策 E**：`unit_testcase` 排除在 artifact `same_as` 体系外。
- **决策 F**：统一 `pipeline_run`（实体标题 `pipeline_run_instance` 废弃）。
- **决策 G-2**：忠实设计文档动词原样落地，不映射到 UModel 权威 6 词表。

### ⚠️ 风险标注

- **R2 破坏性重命名**：已入库的 SLS/CMS EntitySet 全部失效，需重建 workspace 或数据迁移。
- **R6 关系动词非标准（决策 G-2）**：设计文档 13 个动词中仅 `contains`/`same_as`/`relates_to`(≈related_to) 落在 UModel 权威 6 词表内，其余自定义动词能存但**暂无平台标准图语义**（路径/影响/拓扑分析不可用）。UModel 平台 `DataLinkSpec.java:14` TODO 收紧标准动词后，这些自定义动词**可能需要二次迁移**。届时通过 grep 设计文档动词名定位。
- **R8 ACR data_source / id 前缀变更（破坏性）**：ACR 产物的 `data_source` 从 `harbor` 改为 `aliyun_acr`（ACR ≠ Harbor），同时 `docker_image_id`/`artifact_id` 前缀由 `harbor:…` 变为 `aliyun_acr:…`。若已有按 `harbor:` 前缀入库的 docker_image/artifact 数据，需重建或迁移。

### 修复的缺陷（D3–D13）

- D1：清除 `image_sourced_from_image_registry` 悬空配置（data_mapping + 两份 sample）。
- D3：`unit_testcase.test_id` 说明误写"NPM 包"已更正。
- D4：`unit_testcase` 5 个空字段补全。
- D5/D6：`deployment` 补 `title`/`description`/`environment_id`。
- D7：`user` 补 `roles`。
- D8：`artifact.artifact_type` 的 `maven_artifact` 保留枚举、标注暂无 same_as 目标实体。
- D11：统一 `pipeline_run` 命名。
- D12：`docker_image` 的 `architecture`/`os` 取值错配 bug 已修。

### 收尾修复（评审遗留）

- **user.roles 聚合 bug**：`user_task.py` 之前把 `user.roles` 写死为 `[]` 从不填充，灌进 UModel 的 user 记录 roles 恒为空。现改为从该 user 的所有 repository 成员资格聚合 `role` 字段、去重排序。
- **verification 文档失效断言**：`shared/verification/workflow-stages_zh.md` 等的 `git_provider=aliyun` 断言改为 `data_source=codeup`，对齐决策 D。
- **`.mimocode/` 加入 .gitignore**：本地工作产物（与 `.spec/` `.review/` 同类）不再误入版本库。

### Schema 层

- 新增 `tools/gen_umodel_yaml.py`：数据驱动的 schema 生成器，产出 17 EntitySet + 36 EntitySetLink。
- `umodel/entity_set/`：5 → 17；`umodel/entity_set_link/`：12 → 36（29 设计文档关系 + 7 跨域）。
- 新增 13 实体：organization / project / work_item / milestone / pull_request / pipeline / pipeline_run / artifact / helm_chart / binary / npm_package / unit_testcase / deployment。

### Producer 层

- 重命名 git producer：`repository_task` / `user_task` / `release_task`。
- 新增 `pull_request_task` + `IGitAdapter.list_pull_requests()`（GitLab MR / Codeup MR）。
- `image_task` → `docker_image_task`：并入 ACR ListRepository（image_registry 移除），同生 artifact + D12 修复。
- 关系 task 全量重做（`user_owns_repository` / `repository_tags_release` / `repository_contains_pull_request` / `user_participates_in_pull_request` / `release_contains_artifact` / `artifact_same_as_docker_image` / `pod_uses_docker_image`）。
- `orchestrator.py`：注册名、`CRITICAL_GIT_TASKS`、依赖图、运行时就绪判定全部跟随。

### 待办（Phase 4，schema-only，待数据源）

以下实体仅有 schema 定义（EntitySet + EntitySetLink），无 producer，待对应数据源 adapter：
- `organization`（LDAP/钉钉/飞书）
- `project` / `work_item` / `milestone`（Jira/云效）
- `pipeline` / `pipeline_run`（gitlab-ci/云效flow/jenkins）
- `helm_chart` / `binary` / `npm_package`（chartmuseum/artifactory/npm）
- `unit_testcase`（aone）
- `deployment`（云效 appstack/aone）

凭据不可得时按 spec R1 交付 schema-only + mock 单测，不静默降级。
