# Provider Matrix

The `git_provider.type` field in `app_config.yaml` selects which git adapter to load at runtime.

## Supported Providers

| | GitLab | Codeup | GitHub |
|---|---|---|---|
| `git_provider.type` | `gitlab` | `codeup` | `github` |
| Target users | Self-hosted or SaaS GitLab | Alibaba Cloud Codeup / Yunxiao | GitHub.com or GHES |
| SDK | `python-gitlab 4.8.0` | `alibabacloud-devops20210625 3.0.0` | none (stdlib `urllib`, REST API) |
| Authentication | Personal / Project / Group Access Token | RAM AccessKey + Organization ID, or PAT (`auth_mode`) | PAT / fine-grained token (optional — anonymous works for public repos at 60 req/h/IP) |
| API endpoint | User-configured | Default `devops.cn-hangzhou.aliyuncs.com` (overridable) | Default `api.github.com` (overridable for GHES) |
| Default branch fallback | `main` | `master` | `main` |
| `data_source` field value in SLS | `"gitlab"` | `"codeup"` | `"github"` |
| CI pipelines (`pipeline` / `pipeline_run`) | ✓ (GitLab CI, built-in) | not yet (adapter default `[]`) | ✓ via GitHub Actions (standalone `ICIAdapter` on the same `github:` section, `data_source="github_actions"`) |

Standalone CI systems (not git providers) implement `ICIAdapter` and merge into the same
pipeline tasks: **Jenkins** is supported via a `jenkins:` config section (`url`/`user`/`token`,
optional `job_filter` and `repo_mapping` for repository_contains_pipeline edges); **Yunxiao
Flow** via a `yunxiao_flow:` section (`organization_id` + `personal_access_token` PAT against
the standard REST API `openapi-rdc.aliyuncs.com`; RAM AK/SK cannot call Flow APIs for accounts
that never logged into the Yunxiao console, so PAT is required); **GitHub Actions** via the
same `github:` section (`repos`/`organization`/`user` scope, optional token) — wired whenever
that section resolves any repo scope, so it works both when GitHub is the git provider and as
a side-by-side CI source under another provider. GitLab CI
records use `data_source="gitlab_ci"`, GitHub Actions records `data_source="github_actions"`
(CI vs git-hosting sources are distinct per the enum spec).
| Docker Compose | `docker compose up --build` | `docker compose up --build` | `docker compose up --build` |
| Config sample | `app_config.gitlab.yaml.sample` | `app_config.codeup.yaml.sample` | `app_config.github.yaml.sample` |

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

# GitHub
cp devops_data_generator/config/app_config.github.yaml.sample \
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

## GitHub Token and Repo Scope

`github.token` is **optional**: anonymous access reads public repos but is capped at
60 requests/hour/IP. Any token type works — classic PAT with `repo` scope, or a
fine-grained PAT with read-only access (Actions + Contents + Metadata) to the target
repos. GHES is supported via `github.api_url` (e.g. `https://<ghes-host>/api/v3`).

Repo scope is resolved from three combinable knobs, deduplicated by repo id:
`github.repos` (explicit `owner/name` list), `github.organization` (all repos of an
org), `github.user` (all repos of a user). Unreadable repos are skipped with a
warning, never fatal.

Release `commit_sha` is resolved per tag via `git/refs/tags` (annotated tags take one
extra hop) and cached in-process — on a release-heavy repo this saves hundreds of API
calls per cycle.

## Field Alignment

All three providers produce the same entity field set. Only values differ:

| Field | GitLab | Codeup | GitHub |
|---|---|---|---|
| `repository_id` | GitLab project id (string) | Codeup repository id (string) | GitHub repo id (numeric string) |
| `name` | `path_with_namespace` (e.g. `root/demo-app`) | Codeup `name` | `full_name` (`owner/repo`) |
| `url` | `web_url` | Codeup `web_url` | `html_url` |
| `data_source` | `"gitlab"` | `"codeup"` | `"github"` |
| `language` | Primary language from `languages()` | Codeup `language` | `repo.language`; breakdown from `/languages` |
| `default_branch` | API value; fallback `main` | API value; fallback `master` | API value; fallback `main` |

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
any git provider's run. Standalone CD systems are wired only when their config section is present;
GitLab CD is the exception — it is a first-class platform capability that rides on the `gitlab:`
git-provider section and is wired automatically when `git_provider.type: gitlab`. Multiple CD
sources merge into the same `deployment` task (one failing source does not affect the others).

| | Argo CD | GitLab CD | GitHub CD |
|---|---|---|---|
| Config section | `argocd:` in `app_config.yaml` | none — rides on the `gitlab:` git-provider section (auto-wired when `git_provider.type: gitlab`) | none — rides on the `github:` section (auto-wired whenever it resolves any repo scope) |
| SDK | none (stdlib `urllib`, REST API) | `python-gitlab` (Environments/Deployments API) | none (stdlib `urllib`, Deployments/Environments API) |
| Authentication | Bearer token (session token or account API key) | same `gitlab.access_token` as the git provider | same optional `github.token` as the other GitHub axes |
| Tasks enabled | `deployment`, `release_relates_to_deployment` | `deployment`, `release_relates_to_deployment` | `deployment`, `release_relates_to_deployment` |
| `data_source` field value in SLS | `"argocd"` | `"gitlab_cd"` | `"github_cd"` |
| Notes | v3.5.x verified. Do **not** pass `fields` projections to list APIs — the gRPC field mask silently drops `metadata.name` | Deployment `run_id` back-references the `gitlab_ci` pipeline_run id. `gitlab.max_deployments_per_project` (default `20`, `0` = unlimited) caps per-project fetch volume | Deployment `run_id` is parsed back out of the status `log_url` when it points at an Actions job. `github.max_deployments_per_project` (default `20`, `0` = unlimited) caps per-repo fetch volume |

## Providers Not Yet Implemented

Git providers:

- Bitbucket

Deploy providers (implement `IDeployAdapter`):

- Yunxiao AppStack
- Aone

CI providers (implement `ICIAdapter`; GitLab CI 寄生在 IGitAdapter):

- Argo Workflows / Tekton
