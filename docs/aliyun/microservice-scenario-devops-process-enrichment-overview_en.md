# Microservice Scenario: DevOps Process Enrichment Overview

> English summary of [microservice-scenario-devops-process-enrichment-overview.md](microservice-scenario-devops-process-enrichment-overview.md).

## Background

Building on UModel, DevOps process enrichment adds development and release entities to achieve end-to-end data modeling from code to container deployment, integrated with existing APM and K8s observability.

## Core Value

### 1. End-to-End Traceability
- Code change → Release → Image build → Container deployment → Service monitoring
- Every step linked by UModel relationships

### 2. Cross-Domain Data Integration
- Connect development data (repositories, releases, developers) with operations data (services, pods, clusters)
- Enable root cause analysis that spans code changes and runtime behavior

### 3. Responsibility Attribution
- Map developers to repositories, services, and images
- Establish ownership chains for incident response

## Entity Relationship Overview

```
Developer ──manages──→ Code Repository ──sourced_from──→ Code Release
                                                              │
                                                         sourced_from
                                                              ▼
APM Service ◄──sourced_from── Code Release ──→ Image ──→ Image Registry
                                                  │
                                                 uses
                                                  ▼
                                          K8s Pod / Deployment
```

## Supported Git Providers

| Provider | SDK | Authentication |
|---|---|---|
| GitLab (self-hosted / SaaS) | python-gitlab | Access Token (PAT / Project / Group) |
| Codeup (Alibaba Cloud) | alibabacloud-devops20210625 | RAM AK/SK or PAT |
