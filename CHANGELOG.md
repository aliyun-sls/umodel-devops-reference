# Changelog

All notable changes to this repository. Dates are YYYY-MM-DD.

## [Unreleased] — UModel 全量实体对齐（破坏性重命名）

> 权威设计文档 `docs/DevOps UModel设计-new.md`（17 实体 + 29 关系）与对齐 spec
> `docs/umodel-alignment-spec.md`（决策 A–G）均为本地工作产物，已列入 `.gitignore`，
> 不随仓库分发；克隆者请以 `umodel/` 下生成物为准，或自行补齐设计文档。
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

### 图可遍历性修复

- **schema 注册入口**：Compose 新增一次性 `umodel-schema-uploader`，从 gitignore 的 `.env` 读取 AK/SK，幂等 upsert `umodel/` 下 17 个 EntitySet 和 36 条 EntitySetLink。
- **关系端点一致性**：发送前按 `data_mapping.yaml` 的 `topo` 配置将关系端点转换为与节点一致的 entity id，补齐 domain/type/link 字段；`use_field_as_entity_id` 的端点保留原值。
- **CMS 图保活**：producer 生成的 DevOps 实体和关系统一写入 `Update`、observed time、1800 秒 keep-alive 和 first observed time，避免裸 SLS 记录被 EntityStore 判为非活。
- **跨域 Pod 关系**：CMS 数据源的 `k8s.pod` 保留 CMS 原始 entity id，避免重算 id 导致 `pod_uses_docker_image` 边端点悬空。

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

### 增量修复（2026-06 ~ 2026-07）

- **codeup ListRepositoryTags 分页**（8a9b28b）：用 `page_size` 替代 `per_page`，修正 Codeup 标签分页参数。
- **ACR repo_filter**（8a9b28b）：`docker_image_task` 新增 `acr.repo_filter` 白名单，按仓库全命名空间过滤 ACR 拉取范围。
- **ACR fetch pacing 默认 200ms**（8f166ab 系列）：`ListRepoTag` 调用间默认 200ms 节流，防限流而非重试退避。
- **CMS-verify 增强**（6b6886a）：pod→image 拓扑取证 + keep-alive/alias 归一化。

### 代码缺陷修复（Phase 1，2026-07-23）

审计发现的确定性 bug 与逻辑缺陷修复：
- **Codeup PR 死代码**：`list_merge_request_with_options`/`ListMergeRequest` 在 pinned SDK 3.0.0 中不存在；升级 `alibabacloud_devops20210625` 至 5.0.3 并改用 `ListMergeRequestsRequest`/`list_merge_requests_with_options`，Codeup PR 抓取不再静默为空。
- **GitLab MR 作者 id**：对 dict 用 `getattr(author,"id")` 恒空，改 `author.get("id")`。
- **SLS sender 未定义名称 + 校验恒真**：`sls_20201230_models`/`util_models` 未 import，NameError 被 except 吞掉后 `return True`；改用 `LogClient.list_logstore`/`get_project`，异常时 `return False`。
- **`base.py` `get_release_by_tag`**：抽象签名缺 `tag` 参数，补齐为 `(self, repo_id, tag)`。
- **`app.py` logger 先用后定义**：`/invoke`、`/stop`、`main` 的 except 分支早于局部 `logger` 赋值触发 UnboundLocalError；改为模块级 logger。
- **orchestrator 未知任务静默跳过**：对未注册的 enabled 任务名加 warning 并记入 skipped，暴露配置漂移。
- **owns 语义**：`OWNS_ACCESS_LEVEL_THRESHOLD=40` 此前未生效（含 guest 全发 owns 边）；现 `access_level >= 40` 才发 owns 边。
- **ACR 分页截断失效**：短末页 `break` 先于 `max_repositories`/`max_tags_per_repo` 截断；将截断判断移到 break 之前。
- **static 关系缺入图字段**：`static_topo_task` 静态关系补 `__keep_alive_seconds__`。
- **release↔artifact 全局 tag 交叉连边**：改读 `repo_image_mapping.yaml` 按 repo→registry 映射限定匹配，无映射时退回按 tag 匹配（不再跨仓同名 tag 错连）。
- **GitLab release `committed_id`**：拼写错误，改 `commit.get("id")`。
- **reviewers**：两个 adapter 补产出 `reviewers` 键（GitLab/Codeup MR）。
- **MR 未知状态默认值**：两实现统一为 `open`（原 GitLab 为 `draft`）。
- **sample 配置契约补全**：两份 sample 补 `acr.repo_filter`、`fetch_details`、`logstore_mapping.entities.kubernetes_pod`。
- **umodel metric link**：`devops.user_related_to_devops.metric.user_commit` 链名前缀自相矛盾，修正为 `devops.user_related_to_metric.user_commit` 并重新生成 YAML。

### 待办（Phase 4，schema-only，待数据源）

以下实体仅有 schema 定义（EntitySet + EntitySetLink），无 producer，待对应数据源 adapter：
- `organization`（LDAP/钉钉/飞书）
- `project` / `work_item` / `milestone`（Jira/云效）
- `pipeline` / `pipeline_run`（gitlab-ci/云效flow/jenkins）
- `helm_chart` / `binary` / `npm_package`（chartmuseum/artifactory/npm）
- `unit_testcase`（aone）
- `deployment`（云效 appstack/aone）

凭据不可得时按 spec R1 交付 schema-only + mock 单测，不静默降级。
