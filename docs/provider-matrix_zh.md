# 平台矩阵

`app_config.yaml` 中的 `git_provider.type` 字段决定运行时加载哪个 adapter。

## 支持的平台

| | GitLab | Codeup |
|---|---|---|
| `git_provider.type` | `gitlab` | `codeup` |
| 适用场景 | 自建或 SaaS GitLab | 阿里云 Codeup / 云效 |
| SDK | `python-gitlab 4.8.0` | `alibabacloud-devops20210625 3.0.0` |
| 认证方式 | Personal / Project / Group Access Token | RAM AccessKey + Organization ID，或 PAT（`auth_mode`）|
| API 端点 | 用户自配 | 默认 `devops.cn-hangzhou.aliyuncs.com`（可覆盖）|
| 默认分支回退 | `main` | `master` |
| `data_source` 字段值（写入 SLS）| `"gitlab"` | `"codeup"` |
| CI 流水线（`pipeline` / `pipeline_run`） | ✓（GitLab CI，内建） | 未实现（adapter 默认返回 `[]`） |

独立 CI 系统（非 git provider）实现 `ICIAdapter` 并汇入同一对 pipeline 任务：**Jenkins** 已支持（`jenkins:` 配置段，`url`/`user`/`token`，可选 `job_filter` 与 `repo_mapping`）；**云效 Flow** 已支持（`yunxiao_flow:` 配置段，`organization_id` + `personal_access_token` 个人访问令牌，调新版标准 API `openapi-rdc.aliyuncs.com`；注意 RAM AK/SK 对从未登录过云效 console 的账号调不通 Flow 业务 API，必须用 PAT）。GitLab CI 记录用 `data_source="gitlab_ci"`（CI 与代码托管源按枚举规范分开）。
| Docker Compose | `docker compose up --build` | `docker compose up --build` |
| 配置样例 | `app_config.gitlab.yaml.sample` | `app_config.codeup.yaml.sample` |

## 切换平台

```bash
# GitLab
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
docker compose up --build

# Codeup
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
docker compose up --build
```

无需修改代码。

## Codeup 认证模式

通过 `codeup.auth_mode` 选择：

| 模式 | 可见仓库范围 | 配置字段 |
|---|---|---|
| `ram`（默认）| RAM 用户被授权的仓库 | `access_key_id` + `access_key_secret` |
| `pat` | PAT 持有者可见的所有仓库 | `access_key_id` + `access_key_secret` + `access_token` |

AK/SK 始终需要（用于 API 请求签名）。`auth_mode` 仅控制是否发送 PAT 以扩大仓库可见范围。

## GitLab Token 类型

三种 Token 均使用同一个 `gitlab.access_token` 配置字段：

| Token 类型 | 范围 | 使用场景 |
|---|---|---|
| Personal Access Token | 用户级 | 个人使用 |
| Project Access Token | 项目级 | 自动化，不绑定个人账号 |
| Group Access Token | 组级 | 覆盖组内所有项目 |

所需 scope：`api`。

## 字段输出对齐

两个平台产出相同的实体字段集，仅值不同：

| 字段 | GitLab | Codeup |
|---|---|---|
| `repository_id` | GitLab project id（字符串）| Codeup repository id（字符串）|
| `name` | `path_with_namespace`（如 `root/demo-app`）| Codeup `name` |
| `url` | `web_url` | Codeup `web_url` |
| `data_source` | `"gitlab"` | `"codeup"` |
| `language` | `languages()` 排序首位 | Codeup `language` |
| `default_branch` | API 值；回退 `main` | API 值；回退 `master` |

`user.repositories[*].access_level`：GitLab 填实际值（10–50）；Codeup 填 `0`。

`release.release_type`：由 `tasks/utils/release_classifier.py` 统一正则归类。

## 仓库详情抓取

`codeup.fetch_details` / `gitlab.fetch_details`（布尔，默认 `true`）控制 adapter 是否为每个仓库抓取详情（Codeup `GetRepository` / GitLab project detail）以获得更丰富的字段。设为 `false` 可在大组织/大实例下加速，代价是丢失详情级属性。

## 分页与限制

所有列表 API 默认全量分页。`acr:` 下的参数控制拉取范围、节奏与数量：

| 参数 | 类型 | 默认 | 效果 |
|---|---|---|---|
| `acr.repo_filter` | list | `[]`（拉取全部）| 仓库全命名空间名称白名单（如 `["library/nginx"]`）；空 = 拉取实例内所有仓库 |
| `acr.fetch_interval_ms` | int | `200` | ListRepoTag API 调用之间的间隔（毫秒）；属预防性限速，非重试/退避 |
| `acr.max_repositories` | int | `0`（无限）| ACR 镜像仓库最大数 |
| `acr.max_tags_per_repo` | int | `0`（无限）| 每个仓库最大 tag 数 |

## SLS 实体映射

每个实体需在 `sls.logstore_mapping.entities` 下显式配置对应的 SLS logstore（实体名）。其中 `sls.logstore_mapping.entities.kubernetes_pod`（`kubernetes_pod` 实体所用的 logstore）必须存在——缺失时 `kubernetes_pod` 任务会回退到错误的名称，导致 pod 数据写入 SLS 失败。样例见 `app_config.*.yaml.sample` 的 `sls.logstore_mapping.entities` 块。

## 部署平台（独立的轴）

CD/部署系统**不是** git provider——它们实现 `IDeployAdapter`，叠加在任一 git provider 的运行之上。
独立 CD 系统仅在配置段存在时才启用；GitLab CD 例外——它是平台内建能力，寄生在 `gitlab:`
git provider 配置段上，`git_provider.type: gitlab` 时自动接入。多个 CD 源合并进同一个
`deployment` 任务（单源故障不影响其他源）。

| | Argo CD | GitLab CD |
|---|---|---|
| 配置段 | `app_config.yaml` 的 `argocd:` | 无——寄生在 `gitlab:` git provider 配置段（`git_provider.type: gitlab` 时自动接入） |
| SDK | 无（标准库 `urllib`，REST API） | `python-gitlab`（Environments/Deployments API） |
| 认证 | Bearer token（session token 或账号 API key） | 与 git provider 共用 `gitlab.access_token` |
| 启用任务 | `deployment`、`release_relates_to_deployment` | `deployment`、`release_relates_to_deployment` |
| SLS 中 `data_source` 值 | `"argocd"` | `"gitlab_cd"` |
| 备注 | 已在 v3.5.x 验证。**不要**给列表 API 传 `fields` 投影——gRPC field mask 会静默丢掉 `metadata.name` | 部署的 `run_id` 回指 `gitlab_ci` 的 pipeline_run id。`gitlab.max_deployments_per_project`（默认 `20`，`0`=不限）限制单仓库单次采集量 |

## 尚未实现的平台

Git provider：

- GitHub
- Bitbucket

部署 provider（实现 `IDeployAdapter`）：

- 云效 AppStack
- Aone

CI provider（实现 `ICIAdapter`；GitLab CI 寄生在 IGitAdapter）：

- 云效 Flow
- GitHub Actions / Argo Workflows / Tekton
