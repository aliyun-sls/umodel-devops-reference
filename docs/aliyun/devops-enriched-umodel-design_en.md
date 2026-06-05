# UModel Entity Design for DevOps

> English summary of [devops-enriched-umodel-design.md](devops-enriched-umodel-design.md).

## Design Principles

- **Business-oriented**: entity design follows real DevOps workflows.
- **Extensible**: fields accommodate future needs across different tech stacks.
- **Standardized**: follows UModel naming and schema conventions.

## Entity Definitions

### 1. Developer (`devops.developer`)

Core participant in DevOps workflows. Fields: `work_no`, `name`, `email`, `team`, `role`, `department`.

### 2. Code Repository (`devops.code_repository`)

Source code management unit. Fields: `repo_id`, `repo_name`, `repo_url`, `git_provider`, `language`, `framework`, `description`, `default_branch`.

### 3. Code Release (`devops.code_release`)

Transformation from source to deployable artifact. Fields: `release_id`, `repo_id`, `repo_name`, `tag`, `commit_sha`, `release_notes`, `release_time`, `status`, `release_type`, `author`.

### 4. Image Registry (`devops.image_registry`)

Container image storage and distribution. Fields: `registry_id`, `registry_name`, `registry_namespace`, `registry_url`, `provider`, `region`, `description`, `is_public`.

### 5. Container Image (`devops.image`)

Deployable application unit. Fields: `image_id`, `image_name`, `image_tag`, `image_digest`, `registry_id`, `full_image_name`, `build_time`, `size`, `architecture`, `os`, `build_status`.

## Relationship Definitions (12 Links)

| Source | Relation | Target |
|---|---|---|
| `devops.developer` | manages | `devops.code_repository` |
| `devops.developer` | manages | `devops.image_registry` |
| `devops.developer` | manages | `apm.service` |
| `devops.code_release` | sourced_from | `devops.code_repository` |
| `devops.image` | sourced_from | `devops.code_release` |
| `devops.image_registry` | contains | `devops.image` |
| `apm.service` | sourced_from | `devops.code_release` |
| `apm.service` | sourced_from | `devops.code_repository` |
| `k8s.pod` | uses | `devops.image` |
| `k8s.deployment` | uses | `devops.image` |
| `k8s.daemonset` | uses | `devops.image` |
| `k8s.statefulset` | uses | `devops.image` |
