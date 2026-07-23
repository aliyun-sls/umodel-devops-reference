# data_source 枚举规范

> 状态：**枚举基线**，所有 producer 写入实体 `data_source` 字段时的唯一取值来源。
> 关联：`docs/umodel-entity-field-contract.md` §1 引用本文档。
> 背景：决策 D 删除 `git_provider`，统一为 `data_source`；codeup 旧值 `aliyun`（`adapters/codeup/adapter.py:22`）已改为 `codeup`。

## 1. 目的

避免各 adapter 各自造 `data_source` 值导致下游过滤、去重、跨平台用户映射失效。所有实体的 `data_source` 字段只能取本表枚举值。

## 2. 枚举值与适用范围

| data_source | 中文名 | 适用实体 | 来源系统 | 备注 |
|---|---|---|---|---|
| `gitlab` | GitLab | repository/user/release/pull_request/pipeline/pipeline_run | GitLab（self-hosted / SaaS） | |
| `codeup` | 云效代码库 Codeup | repository/user/release/pull_request/pipeline/pipeline_run | 阿里云 Codeup | **不是 `aliyun`**（旧 PROVIDER_NAME 已改） |
| `github` | GitHub | repository/user/release/pull_request/pipeline/pipeline_run | GitHub | |
| `github_actions` | GitHub Actions | pipeline/pipeline_run | GitHub Actions | CI 类，与 git 平台区分 |
| `gitlab_ci` | GitLab CI | pipeline/pipeline_run | GitLab CI/CD | CI 类 |
| `jenkins` | Jenkins | pipeline/pipeline_run | Jenkins | CI 类 |
| `yunxiao` | 云效 Projman | project/work_item/milestone | 云效项目管理 | |
| `yunxiao_flow` | 云效 Flow | pipeline/pipeline_run | 云效流水线 | CI 类 |
| `yunxiao_appstack` | 云效 AppStack | deployment | 云效应用交付 | |
| `jira` | Jira | project/work_item/milestone | Atlassian Jira | Issue tracker |
| `aone` | Aone | unit_testcase/deployment | 内部 Aone 测试/部署 | |
| `harbor` | Harbor | artifact/docker_image | Harbor | 制品库 |
| `aliyun_acr` | 阿里云容器镜像服务 ACR | artifact/docker_image | Alibaba Cloud ACR | ACR 专属；写入 docker_image/artifact 的 `data_source` 与 id 前缀（非 `harbor`） |
| `docker_hub` | Docker Hub | docker_image | Docker Hub | |
| `chartmuseum` | ChartMuseum | artifact/helm_chart | ChartMuseum | Helm 制品库 |
| `artifactory` | JFrog Artifactory | artifact/binary | Artifactory | |
| `nexus` | Sonatype Nexus | artifact/binary | Nexus Repository | |
| `npm_registry` | npm registry | artifact/npm_package | npmjs.org | |
| `verdaccio` | Verdaccio | artifact/npm_package | Verdaccio 私服 | |
| `ldap` | LDAP | organization/user | LDAP 目录 | 组织系统 |
| `dingtalk` | 钉钉 | organization/user | 钉钉通讯录 | 组织系统 |
| `feishu` | 飞书 | organization/user | 飞书通讯录 | 组织系统 |

## 3. 取值规则

1. **小写、下划线分词**：所有值用 `snake_case`，如 `yunxiao_appstack`。
2. **一对一**：每个外部数据源系统对应唯一枚举值；不混用（如 codeup ≠ aliyun ≠ yunxiao，三者各自独立）。
3. **CI vs git 平台区分**：git 平台用 `gitlab`/`codeup`/`github`；CI 系统用 `github_actions`/`gitlab_ci`/`jenkins`/`yunxiao_flow`，即便同一厂商也分开，便于区分「代码托管」与「流水线」两类数据源。
4. **派生实体**：`artifact` 是派生实体（决策 B），其 `data_source` 跟随具体产物来源（如 docker_image 来自 `aliyun_acr`，则对应 artifact 的 `data_source=aliyun_acr`）。

## 4. 已落地变更项

| 位置 | 旧值 | 新值 |
|---|---|---|
| `adapters/codeup/adapter.py:22` `PROVIDER_NAME` | `"aliyun"` | `"codeup"` |
| `adapters/base.py` `get_provider_name()` 文档说明 | 描述为写入 `git_provider` 字段 | 改为写入 `data_source` 字段 |
| 各 task 写入字段名 | `git_provider` | `data_source` |

## 5. 新增枚举流程

若 Phase 4 引入新数据源系统（如 Gitbucket、Bitbucket、Argo CD），新增枚举值须：
1. 先在本文档表格登记（中文名、适用实体、来源系统、备注）；
2. 通知所有 producer 维护者，避免硬编码新值散落各 adapter。
