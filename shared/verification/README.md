# Verification Shared Layer

## Purpose
- `shared/verification/` is the repository-root shared truth layer for the first-wave verification skills.
- It exists so `.codex` and future `.claude` skills can reuse one set of workflow rules instead of copying each other.

## Scope
- workflow stages
- prerequisites
- config contract
- receipt contract
- failure diagnosis routing
- script mapping
- non-portable values

## Non-goals
- not a Python runtime package
- not a replacement for `devops_data_generator/shared`
- not a place to store environment instance values or secrets
- not the place to define `.codex` or `.claude` runtime-specific wrappers

## Canonical Rule
- refresh data into CMS workspace first
- verify visibility second
- diagnose only when refresh or verification does not produce the expected result

## Consumers
- `.codex/skills/verification-*`
- future `.claude` verification skills
- maintainers reading the repository workflow directly
