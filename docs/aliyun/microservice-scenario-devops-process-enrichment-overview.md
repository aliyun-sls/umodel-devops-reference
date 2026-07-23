## **背景与目标**

在可观测 2.0 的 UModel 基础上，微服务场景 DevOps 流程富化旨在通过新增研发、发布、制品、镜像等 UModel 实体，实现从代码开发到容器部署的全链路数据建模，并与现有的 APM 和 K8s 可观测体系深度打通。

> 本场景当前由 `devops_data_generator` 编排生成：DevOps 域 6 个生产实体（user、repository、release、pull_request、artifact、docker_image）+ K8s 域 1 个生产实体（kubernetes_pod），共 7 个生产实体；编排器共 15 个任务，产出的实体与关系数据写入阿里云 SLS（Simple Log Service）LogStore，其中 k8s.pod 拓扑来自 CMS（Cloud Monitor Service）workspace 的 EntityStore。全量 UModel Schema（17 个 EntitySet + 36 个 EntitySetLink）由 `tools/gen_umodel_yaml.py` 生成到 `umodel/`；本场景实际生产子集见 `config/data_mapping.yaml`。

## **核心价值**

### **1. 全链路可追溯**

* **代码到服务**：从 repository（代码仓库）、release（发布）到最终运行的 APM 服务的完整链路。
* **镜像到部署**：从 artifact（制品）与 docker_image（容器镜像）构建到 K8s Pod 部署的完整过程追踪。
* **责任可归属**：明确每个环节的负责人（user），实现问题快速定位。

### **2. 跨域数据融合**

* **DevOps域**：专注于研发流程和制品/镜像管理。
* **APM域**：应用性能监控和服务治理。
* **K8s域**：容器编排和基础设施管理。
* **统一视图**：通过 EntitySetLink 实现跨域数据关联。

### **3. AI友好的数据结构**

* **结构化关系**：为AI分析提供清晰的实体关系图谱。
* **语义化建模**：支持基于业务语义的智能分析。
* **端到端上下文**：为AI提供完整的业务上下文信息。

## **实体域设计**

![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/1614168571/p1008622.png)

* 注意：下述是示例架构和实施方式，实际业务场景中可针对性调整和优化。

### **DevOps域（devops）**

| **实体类型** | **用途** | **核心字段** | **业务价值** |
| --- | --- | --- | --- |
| **用户（user）** | 研发人员信息管理（代指开发、测试、运维、产品等角色） | user_id、full_name、email、display_name、avatar_url、data_source、platform_user_id、department、is_active | 责任归属、团队协作分析 |
| **代码仓库（repository）** | 代码库管理 | repository_id、name、full_path、description、owner_id、language、data_source、platform_repo_id、default_branch、visibility | 技术栈分析、代码质量跟踪 |
| **发布（release）** | 发布记录管理 | release_id、repository_id、version、tag_name、release_type、status、created_by、data_source、platform_release_id | 版本管理、发布质量跟踪 |
| **合并请求（pull_request）** | PR/MR 流程管理 | pr_id、repository_id、number、title、author_id、source_branch、target_branch、status、data_source、platform_pr_id | 代码评审追踪、协作分析 |
| **制品（artifact）** | 构建制品管理（与容器镜像同源派生，决策 B） | artifact_id、repository_id、commit_sha、tag_name、artifact_type、pipeline_run_id、storage_location、data_source | 制品溯源、构建链路追踪 |
| **容器镜像（docker_image）** | 容器镜像信息（含原 image_registry 的 registry 属性，决策 A） | docker_image_id、artifact_id、registry、repository、tag、digest、full_image_name、base_image、architecture、os、data_source | 镜像版本管理、部署追踪 |

> 重命名说明：旧的 `developer`/`code_repository`/`code_release`/`image` 已分别重命名为 `user`/`repository`/`release`/`docker_image`；`image_registry` 实体已移除（决策 A），其 registry 级属性折叠进 `docker_image.registry`。每条记录以 `data_source` 字段作为实体身份与来源判别（GitLab 记录为 `gitlab`，Codeup 记录为 `codeup`——注意不是 `aliyun`；ACR 记录为 `aliyun_acr`）。

### **K8s域（k8s）**

| **实体类型** | **用途** | **核心字段** | **业务价值** |
| --- | --- | --- | --- |
| **K8s Pod（kubernetes_pod）** | 容器编排实例管理 | pod_id、entity_id、images、container_names、namespace、image_count、container_count | 部署实例追踪、镜像使用关联 |

### **与现有域的集成**

#### **APM域集成**

* **服务溯源**：APM 服务可追溯到具体的 repository（代码仓库）和 release（发布版本）。
* **责任归属**：明确服务的负责 user。
* **版本关联**：服务性能问题可快速定位到具体的代码变更。

#### **K8s域集成**

* **镜像关联**：Pod 关联到具体 docker_image。
* **部署追踪**：从 release（发布）到容器部署的完整链路。
* **运维可见性**：运维人员可快速了解部署的服务版本和负责人。

## **关系建模设计**

> 关系名以 `devops_data_generator/tasks/` 中实际注册的任务为准（编排器共 15 个任务）。关系方向与 link_type 见 `config/data_mapping.yaml`。

### **DevOps域内部关系**

```
user            ──owns──►             repository          （user_owns_repository）
repository      ──tags──►             release              （repository_tags_release，方向 repo→release，与旧 sourced_from 相反）
repository      ──contains──►          pull_request        （repository_contains_pull_request）
user            ──participates_in──►  pull_request         （user_participates_in_pull_request，派生自 authors + reviewers）
release         ──contains──►          artifact            （release_contains_artifact）
artifact        ──same_as──►          docker_image         （artifact_same_as_docker_image，ACR 同生派生，决策 B）
```

### **跨域关联关系**

#### **与K8s域的关联**

```
k8s.pod  ──uses──►  docker_image        （pod_uses_docker_image）
```

#### **与APM域的关联**

> 以下关系由 `static_topo` 任务通过静态/混合拓扑模板产出（模板见 `config/static_topo.yaml`）。

```
apm.service  ──sourced_from──►  repository      （apm.service_sourced_from_devops.repository）
apm.service  ──sourced_from──►  release         （apm.service_sourced_from_devops.release）
user         ──manages──►        apm.service   （devops.user_manages_apm.service，旧 developer_manages 重命名）
```

## **应用场景**

### **1. 故障根因分析**

当APM服务出现性能问题时，可以：

* 快速定位到负责的 user。
* 追溯到具体的代码变更和 release（发布版本）。
* 分析是否与最近的 docker_image 更新相关。

### **2. 版本影响分析**

在进行 release（发布）前，可以：

* 分析本次发布将影响哪些APM服务。
* 预测可能影响的K8s工作负载（Pod）。
* 制定回滚策略和风险预案。
* 通知相关的研发和运维人员（user）。

### **3. 安全合规管理**

通过完整的数据链路，可以：

* 审计代码变更的完整流程。
* 跟踪 artifact（制品）与 docker_image 的构建和分发过程。
* 确保部署的镜像来源可信（data_source 可追溯）。
* 实现端到端的安全治理。

### **4. 效能分析优化**

基于丰富的关联数据，可以：

* 分析研发团队的交付效能（user/repository/pull_request 维度）。
* 识别代码到部署的瓶颈环节。
* 优化CI/CD流程配置。
* 提升整体交付质量。

## **技术实现**

### **数据采集**

* **代码仓库/发布/用户/PR 数据**：通过统一适配器接口 `IGitAdapter`（`adapters/base.py`）获取，内置两个实现——GitLab（`adapters/gitlab/adapter.py`，python-gitlab 4.8.0）与 Codeup（`adapters/codeup/adapter.py`，alibabacloud-devops20210625 5.0.3）；`get_provider_name()` 返回值写入每条记录的 `data_source` 字段（`gitlab` 或 `codeup`）。
* **制品与镜像数据**：通过 ACR（Alibaba Cloud Container Registry）producer 在 `docker_image_task` 中一次拉取，同时产出 artifact + docker_image + artifact_same_as_docker_image 关系（决策 B），其 `data_source` 为 `aliyun_acr`。
* **用户数据**：由 Git adapter 的 `list_repository_members()` 输出归一化用户记录；组织域可由 LDAP/钉钉/飞书补充（非本场景主链路）。
* **关联关系**：Git 派生（owns/tags/contains/participates_in）+ ACR 同生派生（same_as）+ static_topo 静态/混合模板（sourced_from/manages）。

### **数据存储**

* **产出落库**：实体与关系数据写入阿里云 SLS（Simple Log Service）LogStore；k8s.pod 实体来自 CMS（Cloud Monitor Service）workspace 的 EntityStore（或本地 kubeconfig）。
* **UModel Schema**：全量定义由 `tools/gen_umodel_yaml.py` 生成到 `umodel/`，共 17 个 EntitySet + 36 个 EntitySetLink；本场景生产上述 7 个实体与 8 类关系（producer 子集见 `config/data_mapping.yaml`）。
* **实时/准实时更新**：通过事件驱动/定时全量机制保持数据实时性和准确性。

## **价值收益**

### **立即收益**

* **数据统一**：建立统一的 DevOps 数据视图。
* **关系透明**：清晰展示代码、镜像、服务间的依赖关系。
* **责任明确**：快速定位问题的负责人和影响范围。

### **中期收益**

* **智能分析**：基于图结构进行深度的关联分析。
* **效能提升**：识别和优化 DevOps 流程中的瓶颈。
* **风险预警**：提前识别潜在的部署和服务风险。

### **长期收益**

* **知识沉淀**：将 DevOps 最佳实践转化为可复用的知识。
* **智能决策**：基于历史数据和关系分析进行智能决策。
* **生态扩展**：为更多 DevOps 工具和流程提供统一的数据基础。
