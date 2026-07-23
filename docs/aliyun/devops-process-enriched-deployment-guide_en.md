# Deployment Guide

> English summary of [devops-process-enriched-deployment-guide.md](devops-process-enriched-deployment-guide.md).

## Prerequisites

- Alibaba Cloud account with ACK, ACR, SLS, and CMS 2.0 enabled.
- A CMS 2.0 Workspace created.
- A git provider configured (GitLab or Codeup).
- Docker and Python 3.9+ installed.

## Deployment Steps

### 1. Upload UModel Schema

```bash
python3 umodel_uploader/umodel_batch_uploader.py umodel \
  --endpoint metrics.<REGION>.aliyuncs.com \
  --workspace <YOUR_WORKSPACE>
```

### 2. Configure `app_config.yaml`

Copy the appropriate sample and fill in credentials:

```bash
# GitLab
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml

# Codeup
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
```

Key config sections: `git_provider`, `acr`, `cms`, `kubernetes`, `sls`, `tasks`. (`git_provider.type` selects the gitlab vs codeup adapter; records write their source into the `data_source` field.)

See [Provider Matrix](../provider-matrix.md) for field details per provider.

### 3. Run Data Generator

```bash
# Single cycle
python3 devops_data_generator/main.py --mode single --config devops_data_generator/config

# Continuous mode (default interval: 300s)
python3 devops_data_generator/main.py --mode continuous --config devops_data_generator/config
```

### 4. Verify in UModel Explorer

```sql
.entity with(domain='devops', type='devops.repository') | limit 0,100
```

Expected: entities with `data_source=gitlab` or `data_source=codeup` depending on your config.

### 5. Docker Compose (optional, self-hosted)

For a long-running self-hosted deployment, create a `docker-compose.yml` inside `devops_data_generator/`:

```yaml
version: '3.8'
services:
  devops-data-generator:
    build: .
    container_name: devops-data-generator
    restart: unless-stopped
    environment:
      PYTHONUNBUFFERED: "1"
    command: ["python3", "main.py", "--mode", "continuous", "--config", "/app/config"]
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
```

```bash
docker compose up -d      # start the long-running generator (continuous mode)
docker compose logs -f    # follow logs
```

Pair `--mode continuous` with `restart: unless-stopped` for a long-running service. Do **not** combine `--mode single` with `unless-stopped`: `single` runs once then exits, and `unless-stopped` would restart it in an infinite loop. For a one-shot run, use `--mode single` with `restart: "no"` or `restart: on-failure` instead.
