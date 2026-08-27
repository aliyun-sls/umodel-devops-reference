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
| `data_source` field value in SLS | `"gitlab"` | `"codeup"` |
| CI pipelines (`pipeline` / `pipeline_run`) | ✓ (GitLab CI, built-in) | not yet (adapter default `[]`) |
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
| `repository_id` | GitLab project id (string) | Codeup repository id (string) |
| `name` | `path_with_namespace` (e.g. `root/demo-app`) | Codeup `name` |
| `url` | `web_url` | Codeup `web_url` |
| `data_source` | `"gitlab"` | `"codeup"` |
| `language` | Primary language from `languages()` | Codeup `language` |
| `default_branch` | API value; fallback `main` | API value; fallback `master` |

`user.repositories[*].access_level`: GitLab fills the actual level (10–50); Codeup fills `0` (concept does not exist).

`release.release_type`: classified by `tasks/utils/release_classifier.py` using word-boundary regex — consistent across providers.

## Repository Detail Fetch

`codeup.fetch_details` / `gitlab.fetch_details` (boolean, default `true`) controls whether the adapter fetches per-repository detail (Codeup `GetRepository` / GitLab project detail) for richer fields. Set to `false` to speed up large orgs/instances at the cost of detail-level attributes.

## Pagination and Limits

All list APIs use full pagination by default. Config parameters under `acr:` control fetch scope, pacing, and volume:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `acr.repo_filter` | list | `[]` (fetch all) | Optional whitelist of repo full-namespace names to fetch (e.g. `["library/nginx"]`); empty = fetch all repos in the instance |
| `acr.fetch_interval_ms` | int | `200` | Pacing between ListRepoTag API calls (ms); prevention, not retry/backoff |
| `acr.max_repositories` | int | `0` (unlimited) | Cap the number of ACR registries fetched |
| `acr.max_tags_per_repo` | int | `0` (unlimited) | Cap the number of image tags per registry |

## SLS Entity Mapping

Each entity needs an explicit SLS logstore (entity name) configured under `sls.logstore_mapping.entities`. In particular, `sls.logstore_mapping.entities.kubernetes_pod` — the logstore used for the `kubernetes_pod` entity — must be present; without it the `kubernetes_pod` task falls back to a wrong name and pod data fails to write to SLS. See the `sls.logstore_mapping.entities` block in `app_config.*.yaml.sample`.

## Deploy Providers (separate axis)

CD/deploy systems are **not** git providers — they implement `IDeployAdapter` and layer on top of
any git provider's run. They are wired only when their config section is present.

| | Argo CD |
|---|---|
| Config section | `argocd:` in `app_config.yaml` |
| SDK | none (stdlib `urllib`, REST API) |
| Authentication | Bearer token (session token or account API key) |
| Tasks enabled | `deployment`, `release_relates_to_deployment` |
| `data_source` field value in SLS | `"argocd"` |
| Notes | v3.5.x verified. Do **not** pass `fields` projections to list APIs — the gRPC field mask silently drops `metadata.name` |

## Providers Not Yet Implemented

Git providers:

- Jenkins
- GitHub Actions / Argo Workflows / Tekton

Deploy providers (implement `IDeployAdapter`):

- Yunxiao AppStack
- Aone
