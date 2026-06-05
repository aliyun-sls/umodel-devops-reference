# Development & Implementation Guide

> English summary of [devops-process-enrichment-development-implementation-guide.md](devops-process-enrichment-development-implementation-guide.md).

## Development Workflow

| Step | Entity Development | Relationship Development |
|---|---|---|
| 1. Define Schema | Define EntitySet YAML | Define EntitySetLink YAML |
| 2. Implement Collection | Fetch data from source API | Generate relationships from entity data |
| 3. Transform Data | Field mapping + entity_id generation | Match source/target entity_id |
| 4. Upload Data | Write to `{workspace}__entity` logstore | Write to `{workspace}__topo` logstore |

## Adapter Architecture

The `IGitAdapter` interface abstracts git provider differences:

```python
class IGitAdapter(ABC):
    def list_repositories(self, fetch_details=True) -> List[Dict]: ...
    def list_repository_members(self, repo_id: str) -> List[Dict]: ...
    def list_repository_releases(self, repo_id: str) -> List[Dict]: ...
    def get_provider_name(self) -> str: ...
    def get_default_branch_fallback(self) -> str: ...
```

Two implementations: `GitLabAdapter` (python-gitlab SDK) and `CodeupAdapter` (alibabacloud SDK).

## Task Types

**Entity tasks** (produce entities):
- `code_repository`, `developer`, `code_release`, `image_registry`, `image`, `kubernetes_pod`

**Relationship tasks** (produce links):
- `code_release_sourced_from_code_repository`, `developer_manages_code_repository`, `image_registry_contains_image`, `image_sourced_from_code_release`, `pod_uses_image`, `static_topo`

## Data Flow

```
Git Provider API → Adapter → Task.fetch_data() → SlsDataGenerator → SlsDataSender → SLS LogStore → CMS EntityStore
```

## Entity ID Generation

Entity IDs are MD5 hashes of primary key fields (defined in `data_mapping.yaml`). This ensures consistent IDs across runs for the same source entity.
