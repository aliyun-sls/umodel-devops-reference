# Verification Skills

## Overview

This repository provides 6 verification skills. Codex and Claude versions share the same names and responsibilities.

The 6 skills form a sequential pipeline:
1. Confirm required resources exist.
2. Confirm workspace and backing SLS project are aligned.
3. Execute refresh to write data into the CMS workspace.
4. After data is written, run visibility and field checks.
5. Diagnose only when refresh or query results are unexpected.

Core principle: `verification-workspace-refresh` writes data first — subsequent queries and checks are meaningless without it.

## Skill List

### 1. `resource-readiness`
**Purpose**: Check whether external resources required by the verification chain exist.
**When to use**: Before any refresh, query, or diagnose.
**Order**: Step 1.

### 2. `workspace-alignment`
**Purpose**: Verify that config points at the correct CMS workspace backing SLS project and entity/topo logstores.
**When to use**: After resources confirmed, before refresh.
**Order**: Step 2.

### 3. `workspace-refresh`
**Purpose**: Execute the canonical refresh — write entity and relationship data to the CMS workspace.
**When to use**: After resource readiness and workspace alignment pass.
**Order**: Step 3.
**Note**: This is the central step. If it doesn't run or writes to the wrong SLS project, downstream checks are meaningless.

### 4. `cms-visibility`
**Purpose**: Check whether `devops.*` entities are visible in the CMS workspace.
**When to use**: After refresh.
**Order**: Step 4.

### 5. `cms-field-check`
**Purpose**: Validate key entity field values. Provider-aware — asserts `git_provider=gitlab` or `=aliyun` based on `app_config.yaml`.
**When to use**: After visibility passes.
**Order**: Step 5.

### 6. `cms-sls-diagnose`
**Purpose**: Diagnose workspace/SLS alignment issues when refresh or visibility results are unexpected.
**When to use**: When any prior step fails.
**Order**: Step 6, failure path only.

## Recommended Order

1. `verification-resource-readiness`
2. `verification-workspace-alignment`
3. `verification-workspace-refresh`
4. `verification-cms-visibility`
5. `verification-cms-field-check`
6. `verification-cms-sls-diagnose` (failure only)

## Receipt Format (Example)

Each skill outputs a structured receipt:

```
- stage: <skill-name>
- git_provider: gitlab | codeup
- verdict: PASS | FAIL | BLOCKED
- [stage-specific fields]
```

See `shared/verification/receipt-contract.md` for the full schema.
