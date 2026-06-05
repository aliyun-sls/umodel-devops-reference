# Provider Matrix

The `git_provider.type` field in `app_config.yaml` selects which git adapter to load at runtime.

## Supported Providers

| | GitLab | Codeup |
|---|---|---|
| `git_provider.type` | `gitlab` | `codeup` |
| Target users | Self-hosted or SaaS GitLab | Alibaba Cloud Codeup / Yunxiao |
| SDK | `python-gitlab 4.8.0` | `alibabacloud-devops20210625 3.0.0` |
| Authentication | Personal / Project / Group Access Token | RAM AccessKey + Organization ID, or PAT (`auth_mode`) |
| API endpoint | User-configured | Default `devops.cn-hangzhou.aliyuncs.com` (overridable) |
| Default branch fallback | `main` | `master` |
| `git_provider` field value in SLS | `"gitlab"` | `"aliyun"` |
| Docker Compose | `docker compose up --build` | `docker compose up --build` |
| Config sample | `app_config.gitlab.yaml.sample` | `app_config.codeup.yaml.sample` |

## Switching Providers

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

No code changes required.

## Codeup Authentication Modes

Codeup supports two authentication modes via `codeup.auth_mode`:

| Mode | Repo visibility | Config fields |
|---|---|---|
| `ram` (default) | Repos granted to the RAM user | `access_key_id` + `access_key_secret` |
| `pat` | All repos visible to the PAT owner | `access_key_id` + `access_key_secret` + `access_token` |

AK/SK is always required for API request signing. `auth_mode` only controls whether the PAT is sent to widen repo scope.

## GitLab Token Types

All three token types use the same `gitlab.access_token` config field:

| Token type | Scope | Use case |
|---|---|---|
| Personal Access Token | User-level | Individual use |
| Project Access Token | Project-level | Automation, not bound to a personal account |
| Group Access Token | Group-level | Covers all projects in a group |

Required scope: `api`.

## Field Alignment

Both providers produce the same entity field set. Only values differ:

| Field | GitLab | Codeup |
|---|---|---|
| `repo_id` | GitLab project id (string) | Codeup repository id (string) |
| `repo_name` | `path_with_namespace` (e.g. `root/demo-app`) | Codeup `name` |
| `repo_url` | `web_url` | Codeup `web_url` |
| `git_provider` | `"gitlab"` | `"aliyun"` |
| `language` | Primary language from `languages()` | Codeup `language` |
| `framework` | `""` (not exposed by GitLab) | Codeup `framework` (if available) |
| `default_branch` | API value; fallback `main` | API value; fallback `master` |

`developer.repositories[*].access_level`: GitLab fills the actual level (10–50); Codeup fills `0` (concept does not exist).

`code_release.release_type`: classified by `tasks/utils/release_classifier.py` using word-boundary regex — consistent across providers.

## Pagination and Limits

All list APIs use full pagination by default. Two config parameters under `acr:` control volume:

| Parameter | Default | Effect |
|---|---|---|
| `max_repositories` | `0` (unlimited) | Cap the number of ACR registries fetched |
| `max_tags_per_repo` | `0` (unlimited) | Cap the number of image tags per registry |

## Providers Not Yet Implemented

- Jenkins — see `adapters/jenkins/README.md`
- GitHub Actions / Argo / Tekton
