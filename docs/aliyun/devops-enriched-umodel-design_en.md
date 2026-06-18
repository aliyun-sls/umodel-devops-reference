# UModel Entity Design for DevOps

> English summary of [devops-enriched-umodel-design.md](devops-enriched-umodel-design.md).

## Design Principles

- **Business-oriented**: entity design follows real DevOps workflows.
- **Extensible**: fields accommodate future needs across different tech stacks.
- **Standardized**: follows UModel naming and schema conventions.

## Entity Definitions

### 1. User (`devops.user`) — *renamed from `devops.developer`*

Core participant in DevOps workflows. Fields: `user_id`, `full_name`, `email`, `data_source`, `platform_user_id`, `department`, `is_active`, `roles` (aggregated from repository membership).

### 2. Repository (`devops.repository`) — *renamed from `devops.code_repository`*

Source code management unit. Fields: `repository_id`, `name`, `url`, `data_source` (replaces old `git_provider`), `owner_id`, `language`, `description`, `default_branch`.

### 3. Release (`devops.release`) — *renamed from `devops.code_release`*

Transformation from source to deployable artifact. Fields: `release_id`, `repository_id`, `tag_name`, `commit_sha`, `description`, `status`, `release_type`, `created_by`.

> Note: the former `devops.image_registry` entity has been **removed** (decision A). Registry-level info now lives as the `docker_image.registry` string field.

### 4. Docker Image (`devops.docker_image`) — *renamed from `devops.image`*

Deployable application unit. Fields: `docker_image_id`, `artifact_id` (decision B pairing), `registry`, `repository`, `tag`, `digest`, `full_image_name`, `architecture`, `os`, `data_source`, `created_at`.

## Relationship Definitions (12 Links)

| Source | Relation | Target |
|---|---|---|
| `devops.user` | owns | `devops.repository` |
| `devops.user` | manages | `apm.service` |
| `devops.repository` | tags | `devops.release` |
| `devops.release` | contains | `devops.artifact` |
| `devops.artifact` | same_as | `devops.docker_image` |
| `apm.service` | sourced_from | `devops.release` |
| `apm.service` | sourced_from | `devops.repository` |
| `k8s.pod` | uses | `devops.docker_image` |
| `k8s.deployment` | uses | `devops.docker_image` |
| `k8s.daemonset` | uses | `devops.docker_image` |
| `k8s.statefulset` | uses | `devops.docker_image` |
