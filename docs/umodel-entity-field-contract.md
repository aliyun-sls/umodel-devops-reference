# UModel 实体字段契约（SSOT）

> 状态：**字段基线**，Phase 1 yaml 落地的唯一字段来源。
> 权威源：`docs/DevOps UModel设计-new.md`（设计文档）。
> 作用：设计文档存在 9 处缺陷（D3–D11，详见 §缺陷修正日志）。本文档以实体表为准，补全空字段、修正错误说明，作为 17 实体字段定义的单一事实源。
> 约定：标 **「设计文档缺失，本契约建议值」** 的字段为本文档推断补全，落地上游若有强约束可回头修正。

---

## 0. 计数声明

设计文档对外宣称「16 个核心实体」，实体表实际列出 **17 行**（含 Unit TestCase 与 Deployment）。这是设计文档自身的计数错误（`-new.md:5` vs `7-25`）。本契约以实体表为准，按 **17 实体** 全量落地。

## 1. data_source 枚举规范

每个实体的 `data_source` 字段取值遵循 `docs/data-source-enum-spec.md` 的统一枚举（本节摘录关键值）：

| data_source 值 | 适用实体 | 来源系统 |
|---|---|---|
| `gitlab` | repository/user/release/pull_request/pipeline/pipeline_run | GitLab（self/SaaS） |
| `codeup` | repository/user/release/pull_request/pipeline/pipeline_run | 阿里云 Codeup（注意：**不是 `aliyun`**） |
| `yunxiao` | work_item/milestone/project/deployment | 云效 Projman / appstack |
| `jira` | work_item/milestone/project | Jira |
| `github` | repository/user/release | GitHub |
| `harbor` | artifact/docker_image | Harbor |
| `chartmuseum` | artifact/helm_chart | ChartMuseum |
| `artifactory` | artifact/binary | Artifactory / Nexus |
| `npm_registry` | artifact/npm_package | npm registry / verdaccio |
| `ldap` / `dingtalk` / `feishu` | organization/user | 组织系统 |
| `aone` | unit_testcase/deployment | Aone 测试/部署 |

**强制**：codeup 的 provider 名（现 `adapters/codeup/adapter.py:22` 硬编码 `"aliyun"`）统一改为 `"codeup"`。

## 2. 主键命名规范

所有实体主键格式：`<data_source>:<platform_*_id>`。主键字段名一律使用 `<entity>_id`：
- `user.user_id`、`repository.repository_id`、`release.release_id`、`docker_image.docker_image_id`
- `organization.organization_id`、`project.project_id`、`work_item.work_item_id`、`milestone.milestone_id`
- `pull_request.pr_id`（沿用设计文档，非 pull_request_id）
- `pipeline.pipeline_id`、`pipeline_run.run_id`（沿用设计文档，非 pipeline_run_id）
- `artifact.artifact_id`、`helm_chart.helm_chart_id`、`binary.binary_id`、`npm_package.npm_package_id`
- `unit_testcase.test_id`、`deployment.deployment_id`

---

## 3. 实体字段定义（17 实体）

### 3.1 organization（devops.organization）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `organization_id` | string | ✓ | ✓ | 组织唯一标识，格式 `<data_source>:<platform_org_id>` |
| `name` | string | ✓ | | 组织名称 |
| `display_name` | string | | | UI 友好名称 |
| `org_type` | enum | ✓ | | company/department/team/group |
| `parent_id` | string | | | 父组织，关联 organization.organization_id |
| `path` | string | | | 如 /company/rd/backend |
| `level` | integer | | | 0 表示根 |
| `description` | string | | | 组织职责 |
| `leader_id` | string | | | 负责人，关联 user.user_id |
| `data_source` | string | ✓ | | ldap/dingtalk/feishu |
| `platform_org_id` | string | ✓ | | 平台组织 ID |
| `url` | string | | | 组织主页 |
| `member_count` | integer | | | 直属成员数 |
| `total_member_count` | integer | | | 含子组织总成员数 |
| `status` | enum | | | active/inactive/dissolved |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |

### 3.2 user（devops.user）← 旧 developer 重命名

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `user_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_user_id>` |
| `work_no` | string | | | 员工工号（降为普通字段，不再作主键） |
| `full_name` | string | ✓ | | 用户全名（旧 `name`→`full_name`） |
| `email` | string | ✓ | | 主邮箱 |
| `display_name` | string | | | UI 友好名称 |
| `avatar_url` | string | | | 头像 URL |
| `data_source` | string | ✓ | | github/gitlab/codeup/yunxiao |
| `platform_user_id` | string | ✓ | | 平台用户 ID |
| `department` | string | | | 组织归属 |
| `is_active` | boolean | | | 是否活跃 |
| `roles` | json | | | **「设计文档缺失，本契约建议值」**：设计文档 JSON 示例含 `roles: ["developer","leader"]`（`-new.md:337`）但字段表无；本契约补入，类型 json，如 `["developer","leader"]` |

> 旧 `developer` 的 `team`、`role` 字段删除（决策：合并为 `roles` json）。

### 3.3 project（devops.project）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `project_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_project_id>` |
| `name` | string | ✓ | | 项目名称 |
| `full_path` | string | | | 如 group/subgroup/project |
| `description` | string | | | 项目描述 |
| `owner_id` | string | ✓ | | 所有者，关联 user.user_id |
| `parent_id` | string | | | 父项目（预留） |
| `data_source` | string | ✓ | | github/gitlab/yunxiao |
| `platform_project_id` | string | ✓ | | 平台项目 ID |
| `url` | string | | | 项目 URL |
| `status` | enum | ✓ | | active/archived/deleted |
| `visibility` | enum | | | public/private/internal |
| `tech_stack` | json | | | 如 `["Java","Spring Boot"]` |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |

### 3.4 work_item（devops.work_item）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `work_item_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_item_id>` |
| `project_id` | string | ✓ | | 关联 project.project_id |
| `title` | string | ✓ | | 标题 |
| `description` | string | | | Markdown 详细描述 |
| `item_type` | enum | ✓ | | feature/bug/task/epic |
| `status` | enum | ✓ | | new/in_progress/testing/done/closed |
| `priority` | enum | | | critical/high/medium/low |
| `creator_id` | string | ✓ | | 创建者，关联 user.user_id |
| `assignee_id` | string | | | 负责人，关联 user.user_id |
| `parent_id` | string | | | 父工作项，支持子任务 |
| `milestone_id` | string | | | 关联 milestone.milestone_id |
| `data_source` | string | ✓ | | jira/github/yunxiao |
| `platform_item_id` | string | ✓ | | 平台工作项 ID |
| `url` | string | | | 工作项 URL |
| `labels` | json | | | 如 `["backend","api"]` |
| `estimated_hours` | double | | | 估算工时 |
| `spent_hours` | double | | | 实际工时 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |
| `closed_at` | datetime | | | 关闭时间 |

### 3.5 milestone（devops.milestone）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `milestone_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_milestone_id>` |
| `project_id` | string | ✓ | | 关联 project.project_id |
| `name` | string | ✓ | | 如 Sprint 10 |
| `description` | string | | | 里程碑目标 |
| `start_time` | datetime | ✓ | | 开始时间 |
| `end_time` | datetime | ✓ | | 计划结束时间 |
| `status` | enum | ✓ | | planned/active/completed/cancelled |
| `data_source` | string | ✓ | | jira/github |
| `platform_milestone_id` | string | ✓ | | 平台里程碑 ID |
| `url` | string | | | 里程碑 URL |
| `planned_capacity` | integer | | | 计划容量 |
| `completed_count` | integer | | | 已完成数 |
| `total_count` | integer | | | 总数 |

### 3.6 repository（devops.repository）← 旧 code_repository 重命名

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `repository_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_repo_id>`（旧 PK `repo_id`→`repository_id`） |
| `name` | string | ✓ | | 仓库名（旧 `repo_name`→`name`） |
| `full_path` | string | | | 如 org/team/user-service |
| `description` | string | | | 仓库描述 |
| `owner_id` | string | ✓ | | 所有者，关联 user.user_id |
| `data_source` | string | ✓ | | github/gitlab/codeup（**替代旧 `git_provider`**，决策 D） |
| `platform_repo_id` | string | ✓ | | 平台仓库 ID |
| `url` | string | | | 仓库 URL（旧 `repo_url`→`url`） |
| `default_branch` | string | | | 如 main/master |
| `visibility` | enum | | | public/private/internal |
| `language` | string | | | 主要语言（**保留**，字段名不变） |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |

> 旧 `framework`、`git_provider` 删除。

### 3.7 pull_request（devops.pull_request）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `pr_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_pr_id>` |
| `project_id` | string | ✓ | | 关联 project.project_id |
| `number` | integer | ✓ | | 项目内唯一编号 |
| `title` | string | ✓ | | 标题 |
| `description` | string | | | Markdown |
| `author_id` | string | ✓ | | 作者，关联 user.user_id |
| `source_branch` | string | ✓ | | 源分支 |
| `target_branch` | string | ✓ | | 目标分支 |
| `source_commit_sha` | string | | | 最新提交 |
| `merge_commit_sha` | string | | | 合并提交 |
| `status` | enum | ✓ | | open/merged/closed/draft |
| `data_source` | string | ✓ | | github/gitlab/codeup |
| `platform_pr_id` | string | ✓ | | 平台 PR ID |
| `url` | string | | | PR URL |
| `commits_count` | integer | | | 提交数 |
| `changed_files` | integer | | | 变更文件数 |
| `additions` | integer | | | 新增行数 |
| `deletions` | integer | | | 删除行数 |
| `comments_count` | integer | | | 评论数 |
| `reviewers` | json | | | 评审者列表 |
| `labels` | json | | | 标签 |
| `has_conflicts` | boolean | | | 是否冲突 |
| `ai_reviewed` | boolean | | | 是否 AI 评审 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |
| `merged_at` | datetime | | | 合并时间 |
| `closed_at` | datetime | | | 关闭时间 |

> 注意：设计文档示例 JSON 含 `repository_id`（`-new.md:572`）但字段表写 `project_id`；本契约以字段表为准用 `project_id`，并在 pull_request 实体**附加 `repository_id`**（关联 repository.repository_id）以支撑 `repository_contains_devops.pull_request` 关系。

### 3.8 pipeline（devops.pipeline）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `pipeline_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_pipeline_id>` |
| `repository_id` | string | ✓ | | 关联 repository.repository_id |
| `name` | string | ✓ | | 流水线名称 |
| `file_path` | string | | | 如 .github/workflows/ci.yml |
| `description` | string | | | 流水线描述 |
| `data_source` | string | ✓ | | github_actions/gitlab_ci/jenkins |
| `platform_pipeline_id` | string | ✓ | | 平台流水线 ID |
| `url` | string | | | 流水线 URL |
| `is_active` | boolean | | | 是否启用 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `updated_at` | datetime | | | 更新时间 |

### 3.9 pipeline_run（devops.pipeline_run）← 旧命名 pipeline_run_instance 统一

> 命名决策 F：设计文档实体标题 `pipeline_run_instance`（`-new.md:636`）与关系表 `pipeline_run`（`-new.md:1202-1204`）不一致，统一为 `pipeline_run`。

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `run_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_run_id>` |
| `pipeline_id` | string | ✓ | | 关联 pipeline.pipeline_id |
| `repository_id` | string | ✓ | | 关联 repository.repository_id |
| `number` | integer | | | 仓库内递增编号 |
| `pr_id` | string | | | 关联 pull_request.pr_id |
| `commit_sha` | string | ✓ | | 触发运行的提交 |
| `branch` | string | | | 触发分支 |
| `trigger_type` | enum | ✓ | | push/pull_request/schedule/manual/tag |
| `status` | enum | ✓ | | queued/in_progress/success/failure/cancelled/skipped |
| `conclusion` | enum | | | success/failure/cancelled/timeout |
| `data_source` | string | ✓ | | github_actions/gitlab_ci/jenkins |
| `platform_run_id` | string | ✓ | | 平台运行 ID |
| `url` | string | | | 运行 URL |
| `triggered_by` | string | | | 触发者，关联 user.user_id |
| `stages` | json | | | 阶段信息 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `started_at` | datetime | | | 开始时间 |
| `completed_at` | datetime | | | 完成时间 |
| `duration_seconds` | integer | | | 执行时长（秒） |
| `queue_duration_seconds` | integer | | | 排队时长（秒） |

### 3.10 artifact（devops.artifact）— 派生抽象实体

> 决策 B：与 docker_image 同源派生（ACR 一次 fetch 同生 artifact + docker_image + artifact_same_as_docker_image）。

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `artifact_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_artifact_id>` |
| `name` | string | ✓ | | 产物名称 |
| `version` | string | ✓ | | 语义化版本 |
| `artifact_type` | enum | ✓ | | docker_image/helm_chart/binary/npm_package/**maven_artifact** |
| `repository_id` | string | ✓ | | 关联 repository.repository_id |
| `commit_sha` | string | ✓ | | 源码提交 |
| `tag_name` | string | | | Git 标签 |
| `pipeline_run_id` | string | ✓ | | 关联 pipeline_run.run_id |
| `storage_location` | string | ✓ | | 存储位置 |
| `size_bytes` | integer | | | 产物大小（字节） |
| `checksum` | string | | | 校验和 |
| `checksum_algorithm` | enum | | | sha256/md5 |
| `security_scan_status` | enum | | | passed/failed/skipped/in_progress |
| `vulnerability_count` | integer | | | 漏洞数 |
| `vulnerability_severity` | json | | | 如 `{"critical":0,"high":2}` |
| `status` | enum | ✓ | | active/deprecated/deleted |
| `data_source` | string | ✓ | | harbor/artifactory/npm_registry |
| `platform_artifact_id` | string | ✓ | | 平台产物 ID |
| `url` | string | | | 产物 URL |
| `metadata` | json | | | 扩展元数据 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `created_by` | string | | | 创建者，关联 user.user_id |

> **maven_artifact 处理（D8）**：`artifact_type` 枚举含 `maven_artifact`（`-new.md:709`），但设计文档无对应实体、无 same_as 关系。本契约保留枚举值，标注「**暂无 same_as 目标实体，schema-only**」；待设计文档补 Maven 实体后再建立 `artifact_same_as_devops.maven_artifact`。

### 3.11 docker_image（devops.docker_image）← 旧 image 重命名

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `docker_image_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_image_id>`（旧 PK `image_id`→`docker_image_id`） |
| `artifact_id` | string | ✓ | | 关联 artifact（same_as） |
| `registry` | string | ✓ | | 镜像仓库（旧 `registry_id`→`registry`；image_registry 实体已移除，决策 A） |
| `repository` | string | ✓ | | 仓库路径（旧 `image_name`→`repository`） |
| `tag` | string | ✓ | | 镜像标签（旧 `image_tag`→`tag`） |
| `digest` | string | ✓ | | 镜像摘要（旧 `image_digest`→`digest`） |
| `full_image_name` | string | ✓ | | 完整镜像名 |
| `base_image` | string | | | 基础镜像 |
| `platform` | string | | | 如 linux/amd64 |
| `architecture` | string | | | amd64/arm64（**修 D12 bug**：取正确架构字段，非 image_size） |
| `os` | string | | | linux/windows（**修 D12 bug**：取正确 OS 字段，非 image_create） |
| `labels` | json | | | Docker 标签 |
| `env_vars` | json | | | 环境变量 |
| `exposed_ports` | array | | | 暴露端口 |
| `volumes` | array | | | 挂载点 |
| `is_signed` | boolean | | | 是否签名 |
| `signature` | string | | | 签名信息 |
| `scan_result` | json | | | 扫描结果详情 |
| `data_source` | string | ✓ | | harbor/docker_hub |
| `platform_image_id` | string | ✓ | | 平台镜像 ID |
| `created_at` | datetime | ✓ | | 创建时间（旧 `build_time`→`created_at`） |

> 旧 `size`、`build_status` 删除。

### 3.12 helm_chart（devops.helm_chart）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `helm_chart_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_chart_id>` |
| `artifact_id` | string | ✓ | | 关联 artifact（same_as） |
| `chart_name` | string | ✓ | | Chart 名称 |
| `chart_version` | string | ✓ | | Chart 版本 |
| `app_version` | string | | | 应用版本 |
| `registry` | string | ✓ | | Chart 仓库 |
| `repository` | string | | | 仓库路径 |
| `description` | string | | | Chart 描述 |
| `home_url` | string | | | 主页 |
| `sources` | array | | | 源码仓库 |
| `maintainers` | array | | | 维护者 |
| `keywords` | array | | | 关键词 |
| `icon` | string | | | 图标 URL |
| `dependencies` | json | | | Chart 依赖 |
| `templates` | array | | | 模板文件 |
| `values_schema` | json | | | values.yaml schema |
| `default_values` | json | | | 默认值 |
| `api_version` | string | | | 如 v2 |
| `type` | enum | | | application/library |
| `deprecated` | boolean | | | 是否废弃 |
| `data_source` | string | ✓ | | chartmuseum/harbor |
| `platform_chart_id` | string | ✓ | | 平台 Chart ID |
| `created_at` | datetime | ✓ | | 创建时间 |

### 3.13 binary（devops.binary）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `binary_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_binary_id>` |
| `artifact_id` | string | ✓ | | 关联 artifact（same_as） |
| `binary_type` | enum | ✓ | | executable/library/archive |
| `file_name` | string | ✓ | | 文件名 |
| `file_extension` | string | | | .jar/.exe/.so/.dll |
| `mime_type` | string | | | MIME 类型 |
| `platform` | string | | | windows/linux/darwin |
| `architecture` | string | | | x86_64/arm64/amd64 |
| `os_version` | string | | | 操作系统版本 |
| `compiler` | string | | | gcc/javac/go |
| `compiler_version` | string | | | 编译器版本 |
| `build_flags` | array | | | 编译选项 |
| `optimization_level` | string | | | 优化级别 |
| `group_id` | string | | | Maven Group ID |
| `artifact_id_maven` | string | | | Maven Artifact ID |
| `classifier` | string | | | 分类器 |
| `packaging` | string | | | jar/war/ear |
| `go_version` | string | | | Go 版本 |
| `module_path` | string | | | Go 模块路径 |
| `has_debug_symbols` | boolean | | | 是否含调试符号 |
| `is_stripped` | boolean | | | 是否剥离符号 |
| `symbol_file_path` | string | | | 符号文件路径 |
| `code_signature` | string | | | 代码签名 |
| `certificate_info` | json | | | 证书信息 |
| `data_source` | string | ✓ | | artifactory/nexus |
| `platform_binary_id` | string | ✓ | | 平台二进制 ID |
| `created_at` | datetime | ✓ | | 创建时间 |

### 3.14 npm_package（devops.npm_package）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `npm_package_id` | string | ✓ | ✓ | 格式 `<data_source>:<platform_package_id>` |
| `artifact_id` | string | ✓ | | 关联 artifact（same_as） |
| `package_name` | string | ✓ | | 如 @company/user-service |
| `scope` | string | | | 如 @company |
| `version` | string | ✓ | | 版本号 |
| `registry` | string | ✓ | | NPM 仓库 |
| `description` | string | | | 包描述 |
| `main_entry` | string | | | 主入口 |
| `types_entry` | string | | | 类型定义入口 |
| `license` | string | | | 许可证 |
| `keywords` | array | | | 关键词 |
| `dependencies` | json | | | 生产依赖 |
| `dev_dependencies` | json | | | 开发依赖 |
| `peer_dependencies` | json | | | 对等依赖 |
| `optional_dependencies` | json | | | 可选依赖 |
| `author` | json | | | 作者 |
| `contributors` | array | | | 贡献者 |
| `homepage` | string | | | 主页 |
| `repository` | json | | | 仓库信息 |
| `bugs` | string | | | Issue Tracker |
| `scripts` | json | | | NPM 脚本 |
| `engines` | json | | | 引擎要求 |
| `files` | array | | | 包含的文件 |
| `dist_tarball` | string | | | Tarball URL |
| `shasum` | string | | | SHA1 校验和 |
| `data_source` | string | ✓ | | npm_registry/verdaccio |
| `platform_package_id` | string | ✓ | | 平台包 ID |
| `created_at` | datetime | ✓ | | 创建时间 |

### 3.15 unit_testcase（devops.unit_testcase）

> 决策 E：unit_testcase **不走 same_as**，排除在 artifact 体系外。

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `test_id` | string | ✓ | ✓ | 测试用例唯一标识，格式 `<data_source>:<platform_test_id>`（**修 D3**：设计文档说明误写「NPM 包唯一标识」，已更正） |
| `repository_id` | string | ✓ | | 关联 repository.repository_id（**修 D4**：设计文档该行全空，本契约补全） |
| `commit_sha` | string | | | 触发测试的提交（**修 D4**：设计文档该行全空，本契约补全） |
| `pipeline_run_id` | string | | | 关联 pipeline_run.run_id（**修 D4**：设计文档该行全空 + 字段名未加反引号，本契约补全并规范化） |
| `name` | string | ✓ | | 名称，如预发单元测试 |
| `result` | string | | | 单测执行结果，如 PASS/FAIL |
| `trigger_by` | json | | | 触发者信息 |
| `url` | string | | | 单测任务 URL |
| `data_source` | string | ✓ | | aone |
| `platform_test_id` | string | ✓ | | 平台测试 ID |
| `created_at` | datetime | ✓ | | 创建时间（**修 D4**：设计文档说明写「包发布时间」，已更正为创建时间） |
| `started_at` | datetime | | | 开始时间（**修 D4**：设计文档说明为空，本契约补全） |
| `completed_at` | datetime | | | 完成时间（**修 D4**：设计文档说明为空，本契约补全） |

### 3.16 release（devops.release）← 旧 code_release 重命名

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `release_id` | string | ✓ | ✓ | 发布唯一标识 |
| `repository_id` | string | ✓ | | 关联 repository.repository_id（旧 `repo_id`→`repository_id`） |
| `name` | string | ✓ | | 发布名称（旧无，新增） |
| `version` | string | ✓ | | 语义化版本 |
| `description` | string | | | 发布说明（旧 `release_notes`→`description`） |
| `release_type` | enum | | | major/minor/patch/hotfix |
| `status` | enum | ✓ | | draft/planned/in_progress/completed/cancelled |
| `data_source` | string | ✓ | | github/gitlab/yunxiao |
| `platform_release_id` | string | ✓ | | 平台发布 ID |
| `url` | string | | | 发布 URL |
| `created_by` | string | ✓ | | 创建者，关联 user.user_id（旧 `author`→`created_by`） |
| `tag_name` | string | | | Git 标签（旧 `tag`→`tag_name`） |
| `target_commitish` | string | | | 目标分支/提交 |
| `artifacts` | json | | | 包含的产物列表 |
| `deployments` | json | | | 部署列表 |
| `pull_requests` | json | | | 包含的 PR 列表 |
| `is_prerelease` | boolean | | | 是否预发布 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `published_at` | datetime | | | 正式发布时间 |
| `completed_at` | datetime | | | 所有部署完成时间 |

> 旧 `repo_name` 删除。

### 3.17 deployment（devops.deployment）

| 字段 | 类型 | 必填 | 主键 | 说明 |
|---|---|---|---|---|
| `deployment_id` | string | ✓ | ✓ | 部署唯一标识，格式 `<data_source>:<platform_deployment_id>` |
| `title` | string | | | 部署标题（**修 D5**：设计文档说明为空，本契约补「部署标题」） |
| `description` | string | | | 部署描述（**修 D5**：设计文档说明为空，本契约补「部署描述」） |
| `repository_id` | string | ✓ | | 关联 repository.repository_id |
| `run_id` | string | | | 关联 pipeline_run.run_id |
| `environment_id` | string | | | 部署环境 ID（**修 D6**：设计文档字段表无此字段，但 JSON 示例含 `environment_id: "yunxiao:ENV-PROD-001"`（`-new.md:1152`），本契约补入） |
| `commit_sha` | string | ✓ | | 部署的代码版本 |
| `version` | string | | | 应用版本号 |
| `status` | enum | ✓ | | queued/in_progress/success/failure/cancelled |
| `conclusion` | enum | | | success/failure/rolled_back |
| `data_source` | string | ✓ | | yunxiao_appstack/aone/github |
| `platform_deployment_id` | string | ✓ | | 平台部署 ID |
| `url` | string | | | 部署 URL |
| `deployed_by` | string | | | 部署人，关联 user.user_id |
| `release_id` | string | | | 关联 release.release_id |
| `artifacts` | json | | | 部署产物 |
| `created_at` | datetime | ✓ | | 创建时间 |
| `started_at` | datetime | | | 开始时间 |
| `completed_at` | datetime | | | 完成时间 |
| `rollback_started_at` | datetime | | | 回滚开始时间（MTTR 计算） |
| `rollback_completed_at` | datetime | | | 回滚完成时间（MTTR 计算） |
| `duration_seconds` | integer | | | 部署时长（秒） |

---

## 4. artifact_id 生成策略（决策 B + R7）

**结论：不复用，各自独立。** ACR 一次 fetch 时：
- `artifact.artifact_id` = `<data_source>:<platform_artifact_id>`（如 `harbor:ARTIFACT-123456`）
- `docker_image.docker_image_id` = `<data_source>:<platform_image_id>`（如 `harbor:IMAGE-123456`）
- 二者通过 `artifact_same_as_devops.docker_image` 关系关联，不共享主键值。

理由：artifact 是跨产物类型的抽象，其 platform_id 来自制品库的通用产物标识；docker_image 的 platform_image_id 来自镜像 registry，二者来源不同，强制复用会引入错配。

---

## 5. 缺陷修正日志（D3–D11）

| 编号 | 缺陷 | 修正位置 |
|---|---|---|
| D3 | `unit_testcase.test_id` 说明误写「NPM 包唯一标识」 | §3.15，更正为测试用例标识 |
| D4 | `unit_testcase` 字段表大面积空白（repository_id/commit_sha/pipeline_run_id 全空 + 时间说明空 + pipeline_run_id 未加反引号） | §3.15，全部补全 |
| D5 | `deployment.title/description` 说明为空 | §3.17，补全 |
| D6 | `deployment` JSON 含 environment_id 但字段表无 | §3.17，补入 |
| D7 | `user` JSON 含 roles 但字段表无 | §3.2，补入（json 类型） |
| D8 | `artifact.artifact_type` 枚举含 maven_artifact 但无对应实体 | §3.10，保留枚举标注「暂无 same_as 目标实体」 |
| D9 | Mermaid 图有 Artifact same_as SlsTemplateVersion，关系表未纳入 | 本契约范围：SlsTemplateVersion 属 SLS 域，非 devops 域，**不在本 17 实体内**；留作跨域扩展 |
| D10 | 设计文档宣称 16 实体，实体表 17 行 | §0，以实体表 17 行为准 |
| D11 | pipeline_run_instance（实体标题）vs pipeline_run（关系表）命名不一致 | §3.9，统一为 pipeline_run（决策 F） |
