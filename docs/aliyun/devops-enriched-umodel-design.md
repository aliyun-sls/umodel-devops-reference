## 案例素材

当前应用案例实现请参考本仓库。

注意：下述是示例架构和实施方式，实际业务场景中可针对性调整和优化。

## **设计原则**

### **1. 业务导向**

* 以DevOps实际业务流程为核心，确保实体设计贴近真实场景。
* 支持端到端的业务流程追踪和分析。
* 面向问题解决，确保关键业务信息可查可用。

### **2. 可扩展性**

* 实体字段设计考虑未来扩展需求。
* 支持不同技术栈和工具链的适配。
* 预留扩展字段，避免频繁的Schema变更。

### **3. 标准化**

* 遵循UModel的设计规范和最佳实践。
* 与现有APM、K8s域保持一致的命名和结构风格。
* 确保字段类型和约束的合理性。

## **实体详细设计**

### **1. 用户实体（devops.user）**（旧 devops.developer 重命名）

#### **业务背景**

用户是DevOps流程的核心参与者，承担代码开发、系统维护、问题处理等关键职责。建立用户实体的目的是实现责任归属的清晰化和问题处理的高效化。

#### **字段设计**

|  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- |
| **字段名称** | **类型** | **必填** | **可过滤** | **可排序** | **描述** | **业务价值** |
| **user_id** | string | 是 | 是 | 是 | 用户标识 | 唯一标识，与企业人员系统对接，作为主键 |
| **full_name** | string | 是 | 是 | 是 | 用户全名 | 直观的人员识别信息 |
| **email** | string | 是 | 是 | 是 | 邮箱地址 | 联系方式，告警通知的重要渠道 |
| **data_source** | string | 是 | 是 | 是 | 数据来源 | 标识来源平台，如gitlab、codeup |
| **platform_user_id** | string | 是 | 是 | 是 | 平台用户ID | 原平台用户标识 |
| **department** | string | 否 | 是 | 是 | 部门 | 组织架构分析，跨部门协作追踪 |
| **is_active** | boolean | 否 | 是 | 是 | 是否活跃 | 过滤离职员工 |
| **roles** | json | 否 | 否 | 否 | 角色列表 | 从该用户在各仓库的成员资格聚合，如 ["developer","leader"] |

### **2. 代码仓库实体（devops.repository）**（旧 devops.code_repository 重命名）

#### **业务背景**

代码仓库是源码管理的核心载体，记录了项目的技术实现和演进历史。通过代码仓库实体，可以实现代码资产的统一管理和服务源头的追溯。

#### **字段设计**

|  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- |
| **字段名称** | **类型** | **必填** | **可过滤** | **可排序** | **描述** | **业务价值** |
| **repository_id** | string | 是 | 是 | 是 | 仓库标识 | 唯一标识，作为主键 |
| **name** | string | 是 | 是 | 是 | 仓库名称 | 仓库的业务标识，通常对应项目名 |
| **url** | string | 是 | 是 | 是 | 仓库URL | 代码访问地址，支持多种Git协议 |
| **data_source** | string | 是 | 是 | 是 | 数据来源 | 替代旧 git_provider，如gitlab、codeup |
| **owner_id** | string | 是 | 是 | 是 | 所有者 | 关联 devops.user.user_id |
| **language** | string | 否 | 是 | 是 | 编程语言 | 主要编程语言，便于技术栈分析 |
| **description** | string | 否 | 否 | 否 | 仓库描述 | 仓库用途说明，便于理解和管理 |
| **default_branch** | string | 是 | 是 | 是 | 默认分支 | 默认分支名称，通常为main或master |

### **3. 代码发布实体（devops.release）**（旧 devops.code_release 重命名）

#### **业务背景**

代码发布记录了从源码到可部署制品的转换过程，是连接开发和运维的关键环节。通过发布实体，可以实现版本管理、变更追踪和回滚分析。

#### **字段设计**

|  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- |
| **字段名称** | **类型** | **必填** | **可过滤** | **可排序** | **描述** | **业务价值** |
| **release_id** | string | 是 | 是 | 是 | 发布ID | 唯一标识，作为主键 |
| **repository_id** | string | 是 | 是 | 是 | 仓库标识 | 关联到具体的代码仓库 |
| **tag_name** | string | 是 | 是 | 是 | 发布标签 | 版本标识，支持语义化版本管理 |
| **commit_sha** | string | 是 | 是 | 是 | 提交SHA | Git提交哈希，精确的代码变更定位 |
| **description** | string | 否 | 否 | 否 | 发布说明 | 发布变更说明，详细的变更描述 |
| **status** | string | 是 | 是 | 是 | 发布状态 | 发布状态，如success、failed、pending等 |
| **release_type** | string | 是 | 是 | 是 | 发布类型 | 发布类型，如major、minor、patch等 |
| **created_by** | string | 是 | 是 | 是 | 创建者 | 关联 devops.user.user_id |

> **注**：旧版 devops.image_registry 实体已移除（决策 A）。registry 级信息折叠为 docker_image.registry 字符串字段，不再作为独立 EntitySet。

### **4. 容器镜像实体（devops.docker_image）**（旧 devops.image 重命名）

#### **业务背景**

容器镜像是应用部署的基本单元，记录了应用的完整运行环境和依赖。通过镜像实体，可以实现从代码构建到容器部署的完整追踪。

#### **字段设计**

|  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- |
| **字段名称** | **类型** | **必填** | **可过滤** | **可排序** | **描述** | **业务价值** |
| **docker_image_id** | string | 是 | 是 | 是 | 镜像标识 | 唯一标识，作为主键 |
| **artifact_id** | string | 是 | 是 | 是 | 构建产物ID | 关联 devops.artifact（决策B同生，same_as关系）|
| **registry** | string | 是 | 是 | 是 | 镜像仓库 | registry 级属性（替代旧 image_registry 实体）|
| **repository** | string | 是 | 是 | 是 | 仓库路径 | 镜像的业务标识，通常对应应用名 |
| **tag** | string | 是 | 是 | 是 | 镜像标签 | 版本标识，支持多版本管理 |
| **digest** | string | 是 | 是 | 是 | 镜像摘要 | SHA256哈希值，确保镜像完整性 |
| **full_image_name** | string | 是 | 是 | 是 | 完整镜像名 | 包含仓库地址的完整镜像名 |
| **architecture** | string | 否 | 是 | 是 | 架构 | CPU架构，如amd64、arm64等 |
| **os** | string | 否 | 是 | 是 | 操作系统 | 基础操作系统，如linux、windows等 |
| **data_source** | string | 是 | 是 | 是 | 数据来源 | 如aliyun_acr |
| **created_at** | timestamp | 是 | 是 | 是 | 创建时间 | 镜像构建的时间记录 |

## **实体关联设计**

### **核心关系类型**

|  |  |  |
| --- | --- | --- |
| **关系类型** | **语义含义** | **典型场景** |
| **manages** | 管理关系 | 责任归属、权限控制 |
| **sourced_from** | 来源关系 | 变更追踪、影响分析 |
| **uses** | 使用关系 | 依赖分析、风险评估 |
| **contains** | 包含关系 | 资源包含、版本管理 |

### **关系类型选择原则**

* **语义明确**：关系类型名称清晰表达业务含义。
* **方向性**：明确关系的方向，支持有向图分析。
* **一致性**：在不同域间保持关系类型的一致性。
* **扩展性**：预留扩展空间，支持新关系类型的添加。

### **DevOps域内部关系**

1. 用户归属代码仓库（devops.user_owns_devops.repository）。

**业务价值**：

* **责任明确**：快速定位代码仓库的负责人。
* **权限管理**：基于归属关系进行权限分配。
* **工作量分析**：统计用户归属的仓库数量和复杂度。

2.代码仓库标记代码发布（devops.repository_tags_devops.release）。

**业务价值**：

* **版本溯源**：快速定位发布版本的源码位置。
* **变更分析**：分析代码变更对发布的影响。
* **质量追踪**：从源码质量到发布质量的端到端追踪。

3.代码发布包含构建产物（devops.release_contains_devops.artifact）。

**业务价值**：

* **产物溯源**：从发布追溯到具体构建产物。
* **多产物支持**：一个发布可含多个制品（镜像/Chart 等）。

4.构建产物对应容器镜像（devops.artifact_same_as_devops.docker_image）。

**业务价值**：

* **镜像溯源**：从容器镜像追溯到具体的代码变更。
* **安全追踪**：快速定位安全漏洞的影响范围。
* **回滚决策**：基于代码变更历史制定回滚策略。

### **跨域关系设计**

#### **与 K8s 域的集成**

1. Pod使用镜像（k8s.pod_uses_devops.docker_image）
2. Deployment使用镜像（k8s.deployment_uses_devops.docker_image）
3. StatefulSet使用镜像（k8s.statefulset_uses_devops.docker_image）
4. DaemonSet使用镜像（k8s.daemonset_uses_devops.docker_image）

**业务价值**：

* **部署追踪**：从K8s工作负载快速定位使用的镜像版本。
* **更新分析**：分析镜像更新对K8s工作负载的影响。
* **回滚支持**：基于镜像版本进行K8s工作负载回滚。

#### **与APM域的集成**

1. 服务来源于代码仓库（apm.service_sourced_from_devops.repository）
2. 服务来源于代码发布（apm.service_sourced_from_devops.release）
3. 用户管理服务（devops.user_manages_apm.service）

**业务价值**：

* **问题定位**：从性能问题快速定位到源码位置。
* **团队协作**：连接运维团队和开发团队的数据视图。
* **责任归属**：明确服务问题的负责人。
* **告警路由**：基于管理关系进行告警通知路由。
