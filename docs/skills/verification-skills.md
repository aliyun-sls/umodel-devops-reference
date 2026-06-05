# Verification Skills

## 概览
本仓库当前提供 6 个 verification skill，Codex 与 Claude 两侧名称和职责保持一致。

这 6 个 skill 不是平铺并列关系，而是串行链路：
1. 先确认资源存在。
2. 再确认 workspace 与 backing SLS project 对齐。
3. 再执行 refresh，把数据真正写入 CMS workspace。
4. 数据写入后，再做 visibility 与 field check。
5. diagnose 只在 refresh 或查询结果异常时进入。

核心原则只有一条：`verification-workspace-refresh` 先把数据写进去，后面的查询与验证才有意义。

## Skill 清单

### 1. `resource-readiness`（`verification-resource-readiness`）
**作用**
- 检查验证链路依赖的外部资源是否已经存在。

**使用时机**
- 任何 refresh、query、diagnose 之前。

**使用顺序**
- 第 1 步。

### 2. `workspace-alignment`（`verification-workspace-alignment`）
**作用**
- 检查当前配置是否对准 CMS workspace backing SLS project 与对应 entity/topo logstore。

**使用时机**
- 资源存在之后，refresh 之前。

**使用顺序**
- 第 2 步。

### 3. `workspace-refresh`（`verification-workspace-refresh`）
**作用**
- 执行 canonical refresh，把实体和关系数据真正刷向 CMS workspace。

**使用时机**
- 资源就绪、workspace 对齐通过之后。

**使用顺序**
- 第 3 步。

**说明**
- 这是整条链路的中心步骤。
- 如果这一步没跑，或者写到了错误的 SLS project，后面的 visibility / field check 都没有意义。
- 这个 skill 对外是主入口，底层才是 `python3 devops_data_generator/main.py --mode single --config devops_data_generator/config`。

### 4. `cms-visibility`（`verification-cms-visibility`）
**作用**
- 检查 CMS workspace 中是否已经能看到 `devops.*` 实体。

**使用时机**
- refresh 之后。

**使用顺序**
- 第 4 步。

### 5. `cms-field-check`（`verification-cms-field-check`）
**作用**
- 检查关键实体字段值是否正确。

**使用时机**
- visibility 已通过之后。

**使用顺序**
- 第 5 步。

### 6. `cms-sls-diagnose`（`verification-cms-sls-diagnose`）
**作用**
- 当 refresh / visibility 结果不符合预期时，诊断 workspace 与 SLS 的对齐问题。

**使用时机**
- 前面任一步失败后。

**使用顺序**
- 第 6 步，仅失败时进入。

## 推荐顺序
1. `verification-resource-readiness`
2. `verification-workspace-alignment`
3. `verification-workspace-refresh`
4. `verification-cms-visibility`
5. `verification-cms-field-check`
6. `verification-cms-sls-diagnose`

## 已验证返回（样例格式）

> 以下是 receipt 的**格式样例**，实际值取决于你的环境配置。
> 每个 stage 跑完后按此格式输出 receipt。

### `resource-readiness`
- 阶段：`resource-readiness`
- git_provider: `gitlab` 或 `codeup`（读自 `app_config.yaml`）
- 结果：`PASS` / `BLOCKED`
- 已确认资源：
  - git provider repository：存在且可达
  - ACR instance：存在
  - CMS workspace：存在
  - 配置文件：6 个必需配置文件存在
- 缺失资源：无 / [列出缺失项]

### `workspace-alignment`
- 阶段：`workspace-alignment`
- 结果：`PASS` / `BLOCKED`
- 已确认：
  - `workspace` = `<配置值>`
  - `sls.project` = `<配置值>`
  - entity logstore 对齐到 `<workspace>__entity`
  - topo logstore 对齐到 `<workspace>__topo`
  - `kubernetes_pod` logstore：已配 / MISSING
  - `k8s.data_source` = `cms` 或 `k8s`

### `workspace-refresh`
- 阶段：`workspace-refresh`
- 结果：`PASS` / `FAIL`
- 执行状态：`success` / `partial_success` / `error`
- 已执行 task 数 / 跳过 / 失败
- 关键实体计数（code_repository / developer / code_release / image_registry / image / kubernetes_pod）
- 关键关系计数

### `cms-visibility`
- 阶段：`cms-visibility`
- 结果：`PASS` / `FAIL`
- devops 域实体分布（各 entity type 计数）
- workspace 总实体数

### `cms-field-check`
- 阶段：`cms-field-check`
- git_provider: `gitlab` 或 `codeup`
- 结果：`PASS` / `FAIL`
- 关键字段断言：
  - `devops.code_repository.git_provider` = `gitlab` 或 `aliyun`（按 provider）
  - `devops.code_release.release_type` 由 release_classifier 归类
  - 其他字段完整性

### `cms-sls-diagnose`
- 用途不是日常主流程，而是失败分支。
- 进入条件通常只有两类：
  - refresh 已执行，但 `cms-visibility` 仍然看不到 `devops.*`
  - workspace / SLS project / logstore 对齐关系可疑
- 典型输出：
  - workspace 对应的 backing SLS project
  - entity / topo logstore 是否存在
  - 当前 workspace 已见 entity types 清单
  - `devops.*` 缺失是否源于写错 project 或 logstore
