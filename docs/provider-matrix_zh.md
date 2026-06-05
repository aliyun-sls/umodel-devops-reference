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
| `git_provider` 字段值（写入 SLS）| `"gitlab"` | `"aliyun"` |
| Docker Compose | `docker-compose.yml`（启动 GitLab CE）| `docker-compose.codeup.yml`（仅 data-generator）|
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
docker compose -f docker-compose.codeup.yml up --build
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
| `repo_id` | GitLab project id（字符串）| Codeup repository id（字符串）|
| `repo_name` | `path_with_namespace`（如 `root/demo-app`）| Codeup `name` |
| `repo_url` | `web_url` | Codeup `web_url` |
| `git_provider` | `"gitlab"` | `"aliyun"` |
| `language` | `languages()` 排序首位 | Codeup `language` |
| `framework` | `""`（GitLab 不暴露）| Codeup `framework`（如可用）|
| `default_branch` | API 值；回退 `main` | API 值；回退 `master` |

`developer.repositories[*].access_level`：GitLab 填实际值（10–50）；Codeup 填 `0`。

`code_release.release_type`：由 `tasks/utils/release_classifier.py` 统一正则归类。

## 分页与限制

所有列表 API 默认全量分页。`acr:` 下两个参数控制拉取量：

| 参数 | 默认 | 效果 |
|---|---|---|
| `max_repositories` | `0`（无限）| ACR 镜像仓库最大数 |
| `max_tags_per_repo` | `0`（无限）| 每个仓库最大 tag 数 |

## 尚未实现的平台

- Jenkins — 见 `adapters/jenkins/README.md`
- GitHub Actions / Argo / Tekton
