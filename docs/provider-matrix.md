# Provider Matrix

新仓将两条 git provider 接入路径合并到同一套抽象（`IGitAdapter`）后，由
配置文件 `git_provider.type` 字段决定运行时实际加载哪一个 adapter。本页
描述「何时用 codeup / 何时用 gitlab」、两套配置切换方式、以及 v0.1 已知
的覆盖范围。

## 支持矩阵

| 维度 | GitLab provider | Codeup provider |
|---|---|---|
| `git_provider.type` 值 | `gitlab` | `codeup` |
| 适用客户 | 自建/SaaS GitLab 用户 | 阿里云 codeup / 云效用户 |
| SDK | `python-gitlab` | `alibabacloud-devops20210625` |
| 认证 | Personal Access Token | RAM AccessKey + Organization ID |
| API endpoint | 客户自定义 | 默认 `devops.cn-hangzhou.aliyuncs.com`，可 override |
| 默认 branch fallback | `main` | `master` |
| `git_provider` 字段值（写入 SLS） | `"gitlab"` | `"aliyun"` |
| Docker Compose 入口 | `docker-compose.yml`（同时启动 GitLab CE 容器）| `docker-compose.codeup.yml`（codeup 是 SaaS，仅启动 data-generator）|
| 配置 sample | `devops_data_generator/config/app_config.gitlab.yaml.sample` | `devops_data_generator/config/app_config.codeup.yaml.sample` |
| 是否 v0.1 端到端真跑通 | ✅ 沿袭 demo 仓 verification PASS receipt | ❌ 待真实环境验证（v0.1 限制） |

## 切换 provider 的最小步骤

```bash
# 选 GitLab
cp devops_data_generator/config/app_config.gitlab.yaml.sample \
   devops_data_generator/config/app_config.yaml
docker compose -f docker-compose.yml up --build

# 选 codeup
cp devops_data_generator/config/app_config.codeup.yaml.sample \
   devops_data_generator/config/app_config.yaml
docker compose -f docker-compose.codeup.yml up --build
```

不需要改任何代码——配置切换即可。

## 字段输出对齐

不同 provider 跑出来的 SLS `devops.code_repository` 实体必须有相同字段集合，
只是 `git_provider` 字段值不同：

| 字段 | GitLab 取值 | Codeup 取值 |
|---|---|---|
| `repo_id` | GitLab project id（字符串化）| Codeup repository id（字符串化）|
| `repo_name` | `path_with_namespace`（如 `root/demo-app`）| Codeup `name` 字段 |
| `repo_url` | `web_url` | Codeup `web_url` |
| `git_provider` | `"gitlab"` | `"aliyun"` |
| `language` | `languages()` 排序后首位 | Codeup `language` |
| `framework` | `""`（GitLab 不暴露此字段）| Codeup `framework`（如可用）|
| `description` | GitLab description | Codeup description |
| `default_branch` | GitLab default_branch；空时 fallback `main` | Codeup default_branch；空时 fallback `master` |

`developer.repositories[*]` 项同时含 `access_level` + `role` 两字段：GitLab
路径填实际 access_level（10/20/30/40/50）；Codeup 路径填 `0`（codeup 概念
不存在 access_level，统一占位）。

`code_release.release_type` 由 `tasks/utils/release_classifier.py` 用统一
正则归类（alpha / beta / release_candidate / hotfix / development / release /
other），两条 provider 路径取值同口径——不再各自启发式。

## v0.1 已知限制

- 真实 Codeup 账号端到端跑通延后到 v0.2（需用户提供 ak/sk + organization）。
  schema / 字段 / adapter 代码已就绪，可基于 mock 字段对照验证。
- Codeup `ListRepositories` + 每仓 `GetRepository` 是 N+1 调用模式。当仓库
  数量过大时（>500）可在配置加 `fetch_details: false` 跳过详情拉取，但会
  丢失 language/framework/description 字段。
- `python-gitlab` 和 `alibabacloud-devops20210625` v0.1 同时安装在
  `requirements.txt`；v0.2 再拆 `extras_require`（`pip install .[gitlab]` /
  `.[codeup]`）。
- 单元测试 / contract test 未引入；v0.1 通过 docker-compose 两套 provider
  端到端跑通作为唯一验证依据，单测留 v0.2。
- env var 覆盖未实现：当前 `git_provider.type` 必须写在 yaml 中，v0.2
  会加 `GIT_PROVIDER` 环境变量优先级。

## 未实现的 provider

- Jenkins — 见 `adapters/jenkins/README.md`
- GitHub Actions / Argo / Tekton — 未在 v0.1 范围
