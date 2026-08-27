"""Generate umodel entity_set / entity_set_link yaml from field contract.

Source of truth: docs/umodel-entity-field-contract.md
Run:  python3 tools/gen_umodel_yaml.py
Writes into umodel/entity_set/ and umodel/entity_set_link/
"""
import os

import yaml

DOMAIN = "devops"
SCHEMA_URL = "umodel.aliyun.com"
SCHEMA_VERSION = "v0.1.0"


def title(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split("_"))


def f(name, typ, zh, en="", required=True, pk=False):
    return {"name": name, "type": typ, "zh": zh, "en": en, "required": required, "pk": pk}


# ---- Entity field definitions (from docs/umodel-entity-field-contract.md) ----

ENTITIES = {
    "organization": {
        "en": "Organization", "zh": "组织",
        "desc_en": "Organization entity representing organizational units (company, department, team) with tree hierarchy.",
        "desc_zh": "组织实体代表组织结构单元，支持树形层级结构。",
        "pk": ["organization_id"],
        "names": ["name", "organization_id", "display_name"],
        "fields": [
            f("organization_id", "string", "组织唯一标识", "Organization unique identifier", pk=True),
            f("name", "string", "组织名称", "Organization name"),
            f("display_name", "string", "显示名称", "Display name", required=False),
            f("org_type", "enum", "组织类型 company/department/team/group", "Organization type: company/department/team/group"),
            f("parent_id", "string", "父组织ID", "Parent organization ID", required=False),
            f("path", "string", "组织路径", "Organization path", required=False),
            f("level", "integer", "组织层级", "Organization level", required=False),
            f("description", "string", "组织描述", "Organization description", required=False),
            f("leader_id", "string", "负责人", "Leader ID", required=False),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_org_id", "string", "平台组织ID", "Platform organization ID"),
            f("url", "string", "组织URL", "Organization URL", required=False),
            f("member_count", "integer", "直属成员数", "Direct member count", required=False),
            f("total_member_count", "integer", "总成员数", "Total member count", required=False),
            f("status", "enum", "状态 active/inactive/dissolved", "Status: active/inactive/dissolved", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
        ],
    },
    "user": {
        "en": "User", "zh": "用户",
        "desc_en": "User entity — core participant of the DevOps process (renamed from developer).",
        "desc_zh": "用户实体是DevOps流程的核心参与者（旧 developer 重命名）。",
        "pk": ["user_id"],
        "names": ["full_name", "user_id", "email"],
        "fields": [
            f("user_id", "string", "用户唯一标识", "User unique identifier", pk=True),
            f("work_no", "string", "员工工号", "Employee number", required=False),
            f("full_name", "string", "用户全名", "User full name"),
            f("email", "string", "主邮箱", "Primary email"),
            f("display_name", "string", "显示名称", "Display name", required=False),
            f("avatar_url", "string", "头像URL", "Avatar URL", required=False),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_user_id", "string", "平台用户ID", "Platform user ID"),
            f("department", "string", "组织归属", "Department", required=False),
            f("is_active", "boolean", "是否活跃", "Is active", required=False),
            f("roles", "json", "角色列表", "Role list", required=False),
        ],
    },
    "project": {
        "en": "Project", "zh": "项目",
        "desc_en": "Project management unit organizing work items and milestones.",
        "desc_zh": "项目实体代表项目管理单元，组织和追踪工作项、里程碑。",
        "pk": ["project_id"],
        "names": ["name", "project_id", "full_path"],
        "fields": [
            f("project_id", "string", "项目唯一标识", "Project unique identifier", pk=True),
            f("name", "string", "项目名称", "Project name"),
            f("full_path", "string", "完整路径", "Full path", required=False),
            f("description", "string", "项目描述", "Project description", required=False),
            f("owner_id", "string", "所有者", "Owner ID"),
            f("parent_id", "string", "父项目ID", "Parent project ID", required=False),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_project_id", "string", "平台项目ID", "Platform project ID"),
            f("url", "string", "项目URL", "Project URL", required=False),
            f("status", "enum", "项目状态 active/archived/deleted", "Project status: active/archived/deleted"),
            f("visibility", "enum", "可见性 public/private/internal", "Visibility: public/private/internal", required=False),
            f("tech_stack", "json", "技术栈", "Tech stack", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
        ],
    },
    "work_item": {
        "en": "Work Item", "zh": "工作项",
        "desc_en": "Unified carrier of requirements, defects, and tasks (Issue/Ticket/Task).",
        "desc_zh": "工作项实体统一抽象各平台Issue、Ticket、Task，是需求、缺陷、任务的统一载体。",
        "pk": ["work_item_id"],
        "names": ["title", "work_item_id", "item_type"],
        "fields": [
            f("work_item_id", "string", "工作项唯一标识", "Work item unique identifier", pk=True),
            f("project_id", "string", "所属项目", "Owning project ID"),
            f("title", "string", "标题", "Title"),
            f("description", "string", "详细描述", "Detailed description", required=False),
            f("item_type", "enum", "工作项类型 feature/bug/task/epic", "Work item type: feature/bug/task/epic"),
            f("status", "enum", "状态 new/in_progress/testing/done/closed", "Status: new/in_progress/testing/done/closed"),
            f("priority", "enum", "优先级 critical/high/medium/low", "Priority: critical/high/medium/low", required=False),
            f("creator_id", "string", "创建者", "Creator ID"),
            f("assignee_id", "string", "负责人", "Assignee ID", required=False),
            f("parent_id", "string", "父工作项ID", "Parent work item ID", required=False),
            f("milestone_id", "string", "所属里程碑", "Owning milestone ID", required=False),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_item_id", "string", "平台工作项ID", "Platform work item ID"),
            f("url", "string", "工作项URL", "Work item URL", required=False),
            f("labels", "json", "标签列表", "Label list", required=False),
            f("estimated_hours", "double", "估算工时", "Estimated hours", required=False),
            f("spent_hours", "double", "实际工时", "Spent hours", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
            f("closed_at", "datetime", "关闭时间", "Closed time", required=False),
        ],
    },
    "milestone": {
        "en": "Milestone", "zh": "里程碑",
        "desc_en": "Team iteration cycle time window (replaces Sprint/Milestone concepts).",
        "desc_zh": "里程碑实体统一替代Sprint、Milestone等概念，用于度量团队迭代周期。",
        "pk": ["milestone_id"],
        "names": ["name", "milestone_id", "status"],
        "fields": [
            f("milestone_id", "string", "里程碑唯一标识", "Milestone unique identifier", pk=True),
            f("project_id", "string", "所属项目", "Owning project ID"),
            f("name", "string", "里程碑名称", "Milestone name"),
            f("description", "string", "里程碑目标", "Milestone goal", required=False),
            f("start_time", "datetime", "开始时间", "Start time"),
            f("end_time", "datetime", "计划结束时间", "Planned end time"),
            f("status", "enum", "状态 planned/active/completed/cancelled", "Status: planned/active/completed/cancelled"),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_milestone_id", "string", "平台里程碑ID", "Platform milestone ID"),
            f("url", "string", "里程碑URL", "Milestone URL", required=False),
            f("planned_capacity", "integer", "计划容量", "Planned capacity", required=False),
            f("completed_count", "integer", "已完成数", "Completed count", required=False),
            f("total_count", "integer", "总数", "Total count", required=False),
        ],
    },
    "repository": {
        "en": "Repository", "zh": "代码仓库",
        "desc_en": "Git repository — core container of code assets (renamed from code_repository).",
        "desc_zh": "代码仓库实体代表Git仓库，是代码资产的核心容器（旧 code_repository 重命名）。",
        "pk": ["repository_id"],
        "names": ["name", "repository_id", "url"],
        "fields": [
            f("repository_id", "string", "仓库唯一标识", "Repository unique identifier", pk=True),
            f("name", "string", "仓库名称", "Repository name"),
            f("full_path", "string", "完整路径", "Full path", required=False),
            f("description", "string", "仓库描述", "Repository description", required=False),
            f("owner_id", "string", "所有者", "Owner ID"),
            f("data_source", "string", "数据来源 github/gitlab/codeup", "Data source: github/gitlab/codeup"),
            f("platform_repo_id", "string", "平台仓库ID", "Platform repository ID"),
            f("url", "string", "仓库URL", "Repository URL", required=False),
            f("default_branch", "string", "默认分支", "Default branch", required=False),
            f("visibility", "enum", "可见性 public/private/internal", "Visibility: public/private/internal", required=False),
            f("language", "string", "主要语言", "Primary language", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
        ],
    },
    "pull_request": {
        "en": "Pull Request", "zh": "代码评审",
        "desc_en": "Code review entity carrying change review, discussion, and merge flow.",
        "desc_zh": "代码评审实体承载代码变更的审查、讨论与合并流程。",
        "pk": ["pr_id"],
        "names": ["title", "pr_id", "status"],
        "fields": [
            f("pr_id", "string", "PR唯一标识", "Pull request unique identifier", pk=True),
            f("project_id", "string", "所属项目", "Owning project ID"),
            f("repository_id", "string", "所属仓库", "Owning repository ID"),
            f("number", "integer", "PR编号", "Pull request number"),
            f("title", "string", "标题", "Title"),
            f("description", "string", "详细描述", "Detailed description", required=False),
            f("author_id", "string", "作者", "Author ID"),
            f("source_branch", "string", "源分支", "Source branch"),
            f("target_branch", "string", "目标分支", "Target branch"),
            f("source_commit_sha", "string", "源提交哈希", "Source commit SHA", required=False),
            f("merge_commit_sha", "string", "合并提交哈希", "Merge commit SHA", required=False),
            f("status", "enum", "状态 open/merged/closed/draft", "Status: open/merged/closed/draft"),
            f("data_source", "string", "数据来源", "Data source"),
            f("platform_pr_id", "string", "平台PR ID", "Platform pull request ID"),
            f("url", "string", "PR URL", "Pull request URL", required=False),
            f("commits_count", "integer", "提交数量", "Commits count", required=False),
            f("changed_files", "integer", "变更文件数", "Changed files count", required=False),
            f("additions", "integer", "新增行数", "Additions", required=False),
            f("deletions", "integer", "删除行数", "Deletions", required=False),
            f("comments_count", "integer", "评论数量", "Comments count", required=False),
            f("reviewers", "json", "评审者列表", "Reviewer list", required=False),
            f("labels", "json", "标签列表", "Label list", required=False),
            f("has_conflicts", "boolean", "是否有冲突", "Has conflicts", required=False),
            f("ai_reviewed", "boolean", "是否AI评审", "AI reviewed", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
            f("merged_at", "datetime", "合并时间", "Merged time", required=False),
            f("closed_at", "datetime", "关闭时间", "Closed time", required=False),
        ],
    },
    "pipeline": {
        "en": "Pipeline", "zh": "流水线",
        "desc_en": "CI/CD pipeline definition/configuration.",
        "desc_zh": "流水线实体代表CI/CD流水线的定义/配置。",
        "pk": ["pipeline_id"],
        "names": ["name", "pipeline_id", "file_path"],
        "fields": [
            f("pipeline_id", "string", "流水线唯一标识", "Pipeline unique identifier", pk=True),
            f("repository_id", "string", "所属仓库", "Owning repository ID"),
            f("name", "string", "流水线名称", "Pipeline name"),
            f("file_path", "string", "配置文件路径", "Config file path", required=False),
            f("description", "string", "流水线描述", "Pipeline description", required=False),
            f("data_source", "string", "数据来源 github_actions/gitlab_ci/jenkins", "Data source: github_actions/gitlab_ci/jenkins"),
            f("platform_pipeline_id", "string", "平台流水线ID", "Platform pipeline ID"),
            f("url", "string", "流水线URL", "Pipeline URL", required=False),
            f("is_active", "boolean", "是否激活", "Is active", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("updated_at", "datetime", "更新时间", "Update time", required=False),
        ],
    },
    "pipeline_run": {
        "en": "Pipeline Run", "zh": "流水线运行",
        "desc_en": "CI/CD pipeline execution instance (unified naming, was pipeline_run_instance).",
        "desc_zh": "流水线运行实体代表CI/CD流水线的执行实例（命名决策F统一为pipeline_run）。",
        "pk": ["run_id"],
        "names": ["run_id", "pipeline_id", "status"],
        "fields": [
            f("run_id", "string", "运行实例唯一标识", "Pipeline run unique identifier", pk=True),
            f("pipeline_id", "string", "所属流水线", "Owning pipeline ID"),
            f("repository_id", "string", "所属仓库", "Owning repository ID"),
            f("number", "integer", "运行编号", "Run number", required=False),
            f("pr_id", "string", "关联PR", "Linked pull request ID", required=False),
            f("commit_sha", "string", "构建提交", "Build commit SHA"),
            f("branch", "string", "分支名", "Branch name", required=False),
            f("trigger_type", "enum", "触发方式 push/pull_request/schedule/manual/tag", "Trigger type: push/pull_request/schedule/manual/tag"),
            f("status", "enum", "运行状态 queued/in_progress/success/failure/cancelled/skipped", "Run status: queued/in_progress/success/failure/cancelled/skipped"),
            f("conclusion", "enum", "运行结论 success/failure/cancelled/timeout", "Run conclusion: success/failure/cancelled/timeout", required=False),
            f("data_source", "string", "数据来源 github_actions/gitlab_ci/jenkins", "Data source: github_actions/gitlab_ci/jenkins"),
            f("platform_run_id", "string", "平台运行ID", "Platform run ID"),
            f("url", "string", "运行URL", "Run URL", required=False),
            f("triggered_by", "string", "触发者", "Triggered by", required=False),
            f("stages", "json", "阶段信息", "Stage information", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("started_at", "datetime", "开始时间", "Start time", required=False),
            f("completed_at", "datetime", "完成时间", "Completion time", required=False),
            f("duration_seconds", "integer", "执行时长(秒)", "Execution duration (seconds)", required=False),
            f("queue_duration_seconds", "integer", "排队时长(秒)", "Queue duration (seconds)", required=False),
        ],
    },
    "artifact": {
        "en": "Artifact", "zh": "构建产物",
        "desc_en": "Abstract/unified entity representing pipeline build artifacts, linked via same_as to concrete types.",
        "desc_zh": "构建产物实体是抽象/通用实体，统一表示流水线构建产生的各类产物（派生实体，决策B）。",
        "pk": ["artifact_id"],
        "names": ["name", "artifact_id", "version"],
        "fields": [
            f("artifact_id", "string", "产物唯一标识", "Artifact unique identifier", pk=True),
            f("name", "string", "产物名称", "Artifact name"),
            f("version", "string", "版本号", "Version"),
            f("artifact_type", "enum", "产物类型 docker_image/helm_chart/binary/npm_package/maven_artifact", "Artifact type: docker_image/helm_chart/binary/npm_package/maven_artifact"),
            f("repository_id", "string", "源代码仓库", "Source repository ID"),
            f("commit_sha", "string", "源码提交", "Source commit SHA"),
            f("tag_name", "string", "Git标签", "Git tag name", required=False),
            f("pipeline_run_id", "string", "构建流水线", "Build pipeline run ID"),
            f("storage_location", "string", "存储位置", "Storage location"),
            f("size_bytes", "integer", "产物大小(字节)", "Artifact size (bytes)", required=False),
            f("checksum", "string", "校验和", "Checksum", required=False),
            f("checksum_algorithm", "enum", "校验算法 sha256/md5", "Checksum algorithm: sha256/md5", required=False),
            f("security_scan_status", "enum", "安全扫描状态 passed/failed/skipped/in_progress", "Security scan status: passed/failed/skipped/in_progress", required=False),
            f("vulnerability_count", "integer", "漏洞数量", "Vulnerability count", required=False),
            f("vulnerability_severity", "json", "漏洞严重级别统计", "Vulnerability severity stats", required=False),
            f("status", "enum", "产物状态 active/deprecated/deleted", "Artifact status: active/deprecated/deleted"),
            f("data_source", "string", "数据来源 harbor/artifactory/npm_registry", "Data source: harbor/artifactory/npm_registry"),
            f("platform_artifact_id", "string", "平台产物ID", "Platform artifact ID"),
            f("url", "string", "产物URL", "Artifact URL", required=False),
            f("metadata", "json", "扩展元数据", "Extension metadata", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("created_by", "string", "创建者", "Created by", required=False),
        ],
    },
    "docker_image": {
        "en": "Docker Image", "zh": "Docker镜像",
        "desc_en": "Docker container image artifact (renamed from image).",
        "desc_zh": "Docker镜像实体代表Docker容器镜像产物（旧 image 重命名）。",
        "pk": ["docker_image_id"],
        "names": ["repository", "docker_image_id", "tag"],
        "fields": [
            f("docker_image_id", "string", "Docker镜像唯一标识", "Docker image unique identifier", pk=True),
            f("artifact_id", "string", "关联的Artifact ID", "Linked artifact ID"),
            f("registry", "string", "镜像仓库", "Image registry"),
            f("repository", "string", "仓库路径", "Repository path"),
            f("tag", "string", "镜像标签", "Image tag"),
            f("digest", "string", "镜像摘要", "Image digest"),
            f("full_image_name", "string", "完整镜像名", "Full image name"),
            f("base_image", "string", "基础镜像", "Base image", required=False),
            f("platform", "string", "平台 如linux/amd64", "Platform, e.g. linux/amd64", required=False),
            f("architecture", "string", "架构 amd64/arm64", "Architecture: amd64/arm64", required=False),
            f("os", "string", "操作系统 linux/windows", "Operating system: linux/windows", required=False),
            f("labels", "json", "Docker标签", "Docker labels", required=False),
            f("env_vars", "json", "环境变量", "Environment variables", required=False),
            f("exposed_ports", "array", "暴露端口", "Exposed ports", required=False),
            f("volumes", "array", "挂载点", "Volumes", required=False),
            f("is_signed", "boolean", "是否签名", "Is signed", required=False),
            f("signature", "string", "签名信息", "Signature", required=False),
            f("scan_result", "json", "扫描结果详情", "Scan result details", required=False),
            f("data_source", "string", "数据来源 harbor/docker_hub", "Data source: harbor/docker_hub"),
            f("platform_image_id", "string", "平台镜像ID", "Platform image ID"),
            f("created_at", "datetime", "创建时间", "Creation time"),
        ],
    },
    "helm_chart": {
        "en": "Helm Chart", "zh": "Helm Chart",
        "desc_en": "Kubernetes application package artifact.",
        "desc_zh": "Helm Chart实体代表Kubernetes应用包产物。",
        "pk": ["helm_chart_id"],
        "names": ["chart_name", "helm_chart_id", "chart_version"],
        "fields": [
            f("helm_chart_id", "string", "Helm Chart唯一标识", "Helm chart unique identifier", pk=True),
            f("artifact_id", "string", "关联的Artifact ID", "Linked artifact ID"),
            f("chart_name", "string", "Chart名称", "Chart name"),
            f("chart_version", "string", "Chart版本", "Chart version"),
            f("app_version", "string", "应用版本", "App version", required=False),
            f("registry", "string", "Chart仓库", "Chart registry"),
            f("repository", "string", "仓库路径", "Repository path", required=False),
            f("description", "string", "Chart描述", "Chart description", required=False),
            f("home_url", "string", "主页URL", "Home URL", required=False),
            f("sources", "array", "源码仓库列表", "Source repository list", required=False),
            f("maintainers", "array", "维护者信息", "Maintainer info", required=False),
            f("keywords", "array", "关键词", "Keywords", required=False),
            f("icon", "string", "图标URL", "Icon URL", required=False),
            f("dependencies", "json", "Chart依赖", "Chart dependencies", required=False),
            f("templates", "array", "模板文件列表", "Template file list", required=False),
            f("values_schema", "json", "values.yaml schema", "values.yaml schema", required=False),
            f("default_values", "json", "默认值", "Default values", required=False),
            f("api_version", "string", "API版本 如v2", "API version, e.g. v2", required=False),
            f("type", "enum", "Chart类型 application/library", "Chart type: application/library", required=False),
            f("deprecated", "boolean", "是否废弃", "Deprecated", required=False),
            f("data_source", "string", "数据来源 chartmuseum/harbor", "Data source: chartmuseum/harbor"),
            f("platform_chart_id", "string", "平台Chart ID", "Platform chart ID"),
            f("created_at", "datetime", "创建时间", "Creation time"),
        ],
    },
    "binary": {
        "en": "Binary", "zh": "二进制文件",
        "desc_en": "Executable/library binary artifact.",
        "desc_zh": "二进制文件实体代表可执行文件、库文件等二进制产物。",
        "pk": ["binary_id"],
        "names": ["file_name", "binary_id", "binary_type"],
        "fields": [
            f("binary_id", "string", "二进制文件唯一标识", "Binary unique identifier", pk=True),
            f("artifact_id", "string", "关联的Artifact ID", "Linked artifact ID"),
            f("binary_type", "enum", "二进制类型 executable/library/archive", "Binary type: executable/library/archive"),
            f("file_name", "string", "文件名", "File name"),
            f("file_extension", "string", "文件扩展名", "File extension", required=False),
            f("mime_type", "string", "MIME类型", "MIME type", required=False),
            f("platform", "string", "平台 windows/linux/darwin", "Platform: windows/linux/darwin", required=False),
            f("architecture", "string", "架构 x86_64/arm64", "Architecture: x86_64/arm64", required=False),
            f("os_version", "string", "操作系统版本", "Operating system version", required=False),
            f("compiler", "string", "编译器", "Compiler", required=False),
            f("compiler_version", "string", "编译器版本", "Compiler version", required=False),
            f("build_flags", "array", "编译选项", "Build flags", required=False),
            f("optimization_level", "string", "优化级别", "Optimization level", required=False),
            f("group_id", "string", "Maven Group ID", "Maven group ID", required=False),
            f("artifact_id_maven", "string", "Maven Artifact ID", "Maven artifact ID", required=False),
            f("classifier", "string", "分类器", "Classifier", required=False),
            f("packaging", "string", "打包类型 jar/war/ear", "Packaging: jar/war/ear", required=False),
            f("go_version", "string", "Go版本", "Go version", required=False),
            f("module_path", "string", "Go模块路径", "Go module path", required=False),
            f("has_debug_symbols", "boolean", "是否包含调试符号", "Has debug symbols", required=False),
            f("is_stripped", "boolean", "是否剥离符号", "Is stripped", required=False),
            f("symbol_file_path", "string", "符号文件路径", "Symbol file path", required=False),
            f("code_signature", "string", "代码签名", "Code signature", required=False),
            f("certificate_info", "json", "证书信息", "Certificate info", required=False),
            f("data_source", "string", "数据来源 artifactory/nexus", "Data source: artifactory/nexus"),
            f("platform_binary_id", "string", "平台二进制ID", "Platform binary ID"),
            f("created_at", "datetime", "创建时间", "Creation time"),
        ],
    },
    "npm_package": {
        "en": "NPM Package", "zh": "NPM包",
        "desc_en": "Node.js package artifact.",
        "desc_zh": "NPM包实体代表Node.js包产物。",
        "pk": ["npm_package_id"],
        "names": ["package_name", "npm_package_id", "version"],
        "fields": [
            f("npm_package_id", "string", "NPM包唯一标识", "NPM package unique identifier", pk=True),
            f("artifact_id", "string", "关联的Artifact ID", "Linked artifact ID"),
            f("package_name", "string", "包名称", "Package name"),
            f("scope", "string", "作用域", "Scope", required=False),
            f("version", "string", "版本号", "Version"),
            f("registry", "string", "NPM仓库", "NPM registry"),
            f("description", "string", "包描述", "Package description", required=False),
            f("main_entry", "string", "主入口文件", "Main entry file", required=False),
            f("types_entry", "string", "类型定义入口", "Type definition entry", required=False),
            f("license", "string", "许可证", "License", required=False),
            f("keywords", "array", "关键词", "Keywords", required=False),
            f("dependencies", "json", "生产依赖", "Production dependencies", required=False),
            f("dev_dependencies", "json", "开发依赖", "Development dependencies", required=False),
            f("peer_dependencies", "json", "对等依赖", "Peer dependencies", required=False),
            f("optional_dependencies", "json", "可选依赖", "Optional dependencies", required=False),
            f("author", "json", "作者信息", "Author info", required=False),
            f("contributors", "array", "贡献者列表", "Contributor list", required=False),
            f("homepage", "string", "主页", "Homepage", required=False),
            f("repository", "json", "仓库信息", "Repository info", required=False),
            f("bugs", "string", "Issue Tracker", "Issue tracker URL", required=False),
            f("scripts", "json", "NPM脚本", "NPM scripts", required=False),
            f("engines", "json", "引擎要求", "Engine requirements", required=False),
            f("files", "array", "包含的文件", "Included files", required=False),
            f("dist_tarball", "string", "Tarball URL", "Tarball URL", required=False),
            f("shasum", "string", "SHA1校验和", "SHA1 checksum", required=False),
            f("data_source", "string", "数据来源 npm_registry/verdaccio", "Data source: npm_registry/verdaccio"),
            f("platform_package_id", "string", "平台包ID", "Platform package ID"),
            f("created_at", "datetime", "创建时间", "Creation time"),
        ],
    },
    "unit_testcase": {
        "en": "Unit TestCase", "zh": "单元测试",
        "desc_en": "Repository unit test artifact. Excluded from artifact same_as system (decision E).",
        "desc_zh": "单元测试产物。排除在artifact same_as体系外（决策E）。",
        "pk": ["test_id"],
        "names": ["name", "test_id", "result"],
        "fields": [
            f("test_id", "string", "测试用例唯一标识", "Test case unique identifier", pk=True),
            f("repository_id", "string", "所属仓库", "Owning repository ID"),
            f("commit_sha", "string", "触发测试的提交", "Commit that triggered the test", required=False),
            f("pipeline_run_id", "string", "关联流水线运行", "Linked pipeline run ID", required=False),
            f("name", "string", "名称", "Name"),
            f("result", "string", "单测执行结果 如PASS/FAIL", "Test result, e.g. PASS/FAIL", required=False),
            f("trigger_by", "json", "触发者信息", "Trigger info", required=False),
            f("url", "string", "单测任务URL", "Test job URL", required=False),
            f("data_source", "string", "数据来源 如aone", "Data source, e.g. aone"),
            f("platform_test_id", "string", "平台测试ID", "Platform test ID"),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("started_at", "datetime", "开始时间", "Start time", required=False),
            f("completed_at", "datetime", "完成时间", "Completion time", required=False),
        ],
    },
    "release": {
        "en": "Release", "zh": "发布",
        "desc_en": "Git repository release/tag (renamed from code_release).",
        "desc_zh": "发布实体代表Git仓库的版本发布标签（旧 code_release 重命名）。",
        "pk": ["release_id"],
        "names": ["name", "release_id", "version"],
        "fields": [
            f("release_id", "string", "发布唯一标识", "Release unique identifier", pk=True),
            f("repository_id", "string", "所属仓库", "Owning repository ID"),
            f("name", "string", "发布名称", "Release name"),
            f("version", "string", "版本号", "Version"),
            f("description", "string", "发布说明", "Release notes", required=False),
            f("release_type", "enum", "发布类型 major/minor/patch/hotfix", "Release type: major/minor/patch/hotfix", required=False),
            f("status", "enum", "发布状态 draft/planned/in_progress/completed/cancelled", "Release status: draft/planned/in_progress/completed/cancelled"),
            f("data_source", "string", "数据来源 github/gitlab/yunxiao", "Data source: github/gitlab/yunxiao"),
            f("platform_release_id", "string", "平台发布ID", "Platform release ID"),
            f("url", "string", "发布URL", "Release URL", required=False),
            f("created_by", "string", "创建者", "Created by"),
            f("tag_name", "string", "Git标签", "Git tag name", required=False),
            f("target_commitish", "string", "目标分支/提交", "Target branch/commit", required=False),
            f("artifacts", "json", "包含的产物列表", "Included artifact list", required=False),
            f("deployments", "json", "部署列表", "Deployment list", required=False),
            f("pull_requests", "json", "包含的PR列表", "Included pull request list", required=False),
            f("is_prerelease", "boolean", "是否预发布", "Is pre-release", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("published_at", "datetime", "正式发布时间", "Published time", required=False),
            f("completed_at", "datetime", "所有部署完成时间", "All-deployments completion time", required=False),
        ],
    },
    "deployment": {
        "en": "Deployment", "zh": "部署",
        "desc_en": "Deployment instance of publishing changes to a specific environment.",
        "desc_zh": "部署实体代表将代码变更发布到特定环境的部署实例。",
        "pk": ["deployment_id"],
        "names": ["deployment_id", "version", "status"],
        "fields": [
            f("deployment_id", "string", "部署唯一标识", "Deployment unique identifier", pk=True),
            f("title", "string", "部署标题", "Deployment title", required=False),
            f("description", "string", "部署描述", "Deployment description", required=False),
            f("repository_id", "string", "代码仓库", "Source repository ID"),
            f("run_id", "string", "关联流水线运行", "Linked pipeline run ID", required=False),
            f("environment_id", "string", "部署环境ID", "Deployment environment ID", required=False),
            f("commit_sha", "string", "部署版本", "Deployed commit SHA"),
            f("version", "string", "应用版本号", "Application version", required=False),
            f("status", "enum", "部署状态 queued/in_progress/success/failure/cancelled", "Deployment status: queued/in_progress/success/failure/cancelled"),
            f("conclusion", "enum", "部署结论 success/failure/rolled_back", "Deployment conclusion: success/failure/rolled_back", required=False),
            f("data_source", "string", "数据来源 yunxiao_appstack/aone/github/argocd", "Data source: yunxiao_appstack/aone/github/argocd"),
            f("platform_deployment_id", "string", "平台部署ID", "Platform deployment ID"),
            f("url", "string", "部署URL", "Deployment URL", required=False),
            f("deployed_by", "string", "部署人", "Deployed by", required=False),
            f("release_id", "string", "所属发布", "Owning release ID", required=False),
            f("artifacts", "json", "部署产物", "Deployed artifacts", required=False),
            f("created_at", "datetime", "创建时间", "Creation time"),
            f("started_at", "datetime", "开始时间", "Start time", required=False),
            f("completed_at", "datetime", "完成时间", "Completion time", required=False),
            f("rollback_started_at", "datetime", "回滚开始时间", "Rollback start time", required=False),
            f("rollback_completed_at", "datetime", "回滚完成时间", "Rollback completion time", required=False),
            f("duration_seconds", "integer", "部署时长(秒)", "Deployment duration (seconds)", required=False),
        ],
    },
}


# ---- Link definitions (29 design-doc relations + cross-domain) ----
# Each: (filename_key, link_name, src_entity, dest_entity, link_type, priority)
LINKS = [
    # design-doc 29 relations (spec §4.1)
    ("organization_contains_user", "devops.organization_contains_devops.user", "organization", "user", "contains", 5),
    ("organization_contains_organization", "devops.organization_contains_devops.organization", "organization", "organization", "contains", 5),
    ("user_participates_in_work_item", "devops.user_participates_in_devops.work_item", "user", "work_item", "participates_in", 5),
    ("user_participates_in_pull_request", "devops.user_participates_in_devops.pull_request", "user", "pull_request", "participates_in", 5),
    ("user_owns_project", "devops.user_owns_devops.project", "user", "project", "owns", 5),
    ("user_owns_repository", "devops.user_owns_devops.repository", "user", "repository", "owns", 5),
    ("user_related_to_metric_user_commit", "devops.user_related_to_metric.user_commit", "user", "metric.user_commit", "related_to", 5),
    ("user_related_to_metric_user_project_participation", "devops.user_related_to_metric.user_project_participation", "user", "metric.user_project_participation", "related_to", 5),
    ("project_contains_work_item", "devops.project_contains_devops.work_item", "project", "work_item", "contains", 5),
    ("project_contains_milestone", "devops.project_contains_devops.milestone", "project", "milestone", "contains", 5),
    ("project_relates_to_repository", "devops.project_relates_to_devops.repository", "project", "repository", "relates_to", 5),
    ("project_tracks_pull_request", "devops.project_tracks_devops.pull_request", "project", "pull_request", "tracks", 5),
    ("milestone_schedules_work_item", "devops.milestone_schedules_devops.work_item", "milestone", "work_item", "schedules", 5),
    ("work_item_parent_of_work_item", "devops.work_item_parent_of_devops.work_item", "work_item", "work_item", "parent_of", 5),
    ("work_item_implements_pull_request", "devops.work_item_implements_devops.pull_request", "work_item", "pull_request", "implements", 5),
    ("repository_contains_pull_request", "devops.repository_contains_devops.pull_request", "repository", "pull_request", "contains", 5),
    ("repository_contains_pipeline", "devops.repository_contains_devops.pipeline", "repository", "pipeline", "contains", 5),
    ("repository_tags_release", "devops.repository_tags_devops.release", "repository", "release", "tags", 5),
    ("pull_request_triggers_pipeline_run", "devops.pull_request_triggers_devops.pipeline_run", "pull_request", "pipeline_run", "triggers", 5),
    ("pipeline_instantiates_pipeline_run", "devops.pipeline_instantiates_devops.pipeline_run", "pipeline", "pipeline_run", "instantiates", 5),
    ("pipeline_run_builds_artifact", "devops.pipeline_run_builds_devops.artifact", "pipeline_run", "artifact", "builds", 5),
    ("artifact_same_as_docker_image", "devops.artifact_same_as_devops.docker_image", "artifact", "docker_image", "same_as", 5),
    ("artifact_same_as_helm_chart", "devops.artifact_same_as_devops.helm_chart", "artifact", "helm_chart", "same_as", 5),
    ("artifact_same_as_binary", "devops.artifact_same_as_devops.binary", "artifact", "binary", "same_as", 5),
    ("artifact_same_as_npm_package", "devops.artifact_same_as_devops.npm_package", "artifact", "npm_package", "same_as", 5),
    ("release_contains_artifact", "devops.release_contains_devops.artifact", "release", "artifact", "contains", 5),
    ("docker_image_deploys_as_deployment", "devops.docker_image_deploys_as_devops.deployment", "docker_image", "deployment", "deploys_as", 5),
    ("helm_chart_deploys_as_deployment", "devops.helm_chart_deploys_as_devops.deployment", "helm_chart", "deployment", "deploys_as", 5),
    ("release_relates_to_deployment", "devops.release_relates_to_devops.deployment", "release", "deployment", "relates_to", 5),
    # cross-domain (spec §4.2) — src/dest may be non-devops
    ("k8s_pod_uses_docker_image", "k8s.pod_uses_devops.docker_image", "k8s.pod", "docker_image", "uses", 5),
    ("k8s_deployment_uses_docker_image", "k8s.deployment_uses_devops.docker_image", "k8s.deployment", "docker_image", "uses", 5),
    ("k8s_daemonset_uses_docker_image", "k8s.daemonset_uses_devops.docker_image", "k8s.daemonset", "docker_image", "uses", 5),
    ("k8s_statefulset_uses_docker_image", "k8s.statefulset_uses_devops.docker_image", "k8s.statefulset", "docker_image", "uses", 5),
    ("apm_service_sourced_from_repository", "apm.service_sourced_from_devops.repository", "apm.service", "repository", "sourced_from", 5),
    ("apm_service_sourced_from_release", "apm.service_sourced_from_devops.release", "apm.service", "release", "sourced_from", 5),
    ("user_manages_apm_service", "devops.user_manages_apm.service", "user", "apm.service", "manages", 5),
]


def dump_doc(doc: dict) -> str:
    # safe_dump 保证输出永远可解析：描述文本含冒号等特殊字符时会自动加引号。
    # allow_unicode 保留中文原文；sort_keys=False 保持字段书写顺序。
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False)


def gen_entity(name, meta):
    fields = []
    for fld in meta["fields"]:
        t = fld["type"]
        blob = t in ("json", "array")
        disp = title(fld["name"])
        fields.append({
            "description": {"en_us": fld.get("en") or fld["zh"], "zh_cn": fld["zh"]},
            "display_name": {"en_us": disp, "zh_cn": fld["zh"]},
            "filterable": not blob,
            "name": fld["name"],
            "orderable": not blob,
            "short_description": {"en_us": disp, "zh_cn": fld["zh"]},
            "type": t,
        })
    return dump_doc({
        "kind": "entity_set",
        "metadata": {
            "description": {"en_us": meta["desc_en"], "zh_cn": meta["desc_zh"]},
            "display_name": {"en_us": meta["en"], "zh_cn": meta["zh"]},
            "domain": DOMAIN,
            "kind": "entity_set",
            "name": f"{DOMAIN}.{name}",
        },
        "schema": {"url": SCHEMA_URL, "version": SCHEMA_VERSION},
        "spec": {
            "dynamic": False,
            "fields": fields,
            "keep_alive_seconds": 86400,
            "name_fields": list(meta["names"]),
            "primary_key_fields": list(meta["pk"]),
            "time_field": "__time__",
            "type": "entity_set",
        },
    })


def parse_ref(ref):
    """ref like 'user' (devops) or 'k8s.pod' (other domain) or 'metric.user_commit'."""
    if "." in ref:
        parts = ref.split(".", 1)
        domain, ent = parts[0], parts[1]
        if "." in ent:
            domain = ref.split(".")[0]
        full = ref
    else:
        domain, ent, full = DOMAIN, ref, f"{DOMAIN}.{ref}"
    return domain, ent, full


def gen_link(key, link_name, src, dest, ltype, priority):
    src_d, _, src_full = parse_ref(src)
    dest_d, _, dest_full = parse_ref(dest)
    src_cap = src.split(".")[-1].replace("_", " ").title()
    dest_cap = dest.split(".")[-1].replace("_", " ").title()
    return dump_doc({
        "kind": "entity_set_link",
        "metadata": {
            "description": {
                "en_us": f"{src_cap} {ltype} {dest_cap}.",
                "zh_cn": f"{src_cap} {ltype} {dest_cap}。",
            },
            "display_name": {
                "en_us": f"{src_cap} {ltype.title()} {dest_cap}",
                "zh_cn": f"{src_cap} {ltype} {dest_cap}",
            },
            "domain": DOMAIN,
            "kind": "entity_set_link",
            "name": link_name,
        },
        "schema": {"url": SCHEMA_URL, "version": SCHEMA_VERSION},
        "spec": {
            "dest": {"domain": dest_d, "kind": "entity_set", "name": dest_full},
            "entity_link_type": ltype,
            "priority": priority,
            "src": {"domain": src_d, "kind": "entity_set", "name": src_full},
        },
    })


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eset_dir = os.path.join(base, "umodel", "entity_set")
    elink_dir = os.path.join(base, "umodel", "entity_set_link")
    os.makedirs(eset_dir, exist_ok=True)
    os.makedirs(elink_dir, exist_ok=True)

    for name, meta in ENTITIES.items():
        path = os.path.join(eset_dir, f"devops_devops.{name}.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(gen_entity(name, meta))
        print(f"entity_set: {path}")

    for (key, link_name, src, dest, ltype, prio) in LINKS:
        path = os.path.join(elink_dir, f"{link_name}.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(gen_link(key, link_name, src, dest, ltype, prio))
        print(f"entity_set_link: {path}")

    print(f"\nGenerated {len(ENTITIES)} EntitySet + {len(LINKS)} EntitySetLink files.")


if __name__ == "__main__":
    main()
