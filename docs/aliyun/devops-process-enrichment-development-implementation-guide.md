本文以 DevOps 场景为例，展示如何从业务需求出发，一步步开发实体数据和关系数据。

## **开发流程概览**

开发实体数据和关系数据遵循如下统一的流程：

|  |  |  |
| --- | --- | --- |
| **步骤** | **实体开发** | **关系开发** |
| **1. 定义Schema** | 定义 EntitySet | 定义 EntitySetLink |
| **2. 实现数据采集** | 从数据源获取实体数据 | 从实体数据或配置生成关系 |
| **3. 数据转换** | 字段映射、生成 entity_id | 匹配源和目标 entity_id |
| **4. 上传数据** | 上传到`${workspace}__entity` logstore | 上传到`${workspace}__topo` logstore |

此处以常见微服务DevOps场景为例，演示实体和关系的完整开发流程。

**DevOps典型流程**：

1. **开发阶段**：研发人员在GitLab中创建和管理代码仓库。
2. **发布阶段**：代码合并后打Tag，创建代码发布记录。
3. **构建阶段**：CI流程根据代码发布构建容器镜像。
4. **存储阶段**：容器镜像推送到ACR镜像仓库。
5. **部署阶段**：K8s从镜像仓库拉取镜像，部署Pod实例。
6. **监控阶段**：APM系统监控运行中的服务性能。

本文对应实现示例请参考 `umodel-gitlab-devops-demo` 示例仓库，项目目录如下：

```
├── devops_data_generator/           # 数据生成器主目录
│   ├── config/                      # 配置文件
│   │   ├── app_config.yaml.sample   # 应用配置样例
│   │   ├── config_loader.py         # 配置加载器
│   │   ├── data_mapping.yaml        # 实体/关系字段映射配置
│   │   ├── manage_mapping.yaml      # 管理关系配置
│   │   ├── static_topo.yaml         # 静态关系配置
│   │   └── repo_image_mapping.yaml  # 代码仓库与镜像仓库映射
│   ├── tasks/                       # 任务实现
│   ├── generator/                   # 数据生成器
│   ├── sender/                      # 数据发送器
│   ├── shared/                      # 共享组件
│   ├── scripts/                     # 验证与诊断脚本
│   ├── orchestrator.py              # 任务编排器
│   ├── main.py                      # 命令行入口
│   ├── app.py                       # 应用入口
│   ├── Dockerfile                   # Docker构建文件
│   └── requirements.txt             # Python依赖
├── umodel/                          # UModel Schema定义
├── umodel_uploader/                 # UModel上传工具
├── shared/verification/             # verification共享规则
├── .codex/skills/                   # Codex skills
└── .claude/skills/                  # Claude skills
```

**说明**

完整介绍该场景实体和关系的开发过程会过于冗长，**因此以其中开发人员实体（developer）和管理关系（manages）为例**，演示从Schema定义到数据上传的完整开发过程。**UModel的实体建模方法、关系建模方法、数据采集流程、上传策略等开发流程是通用的，**其他实体和关系的开发具体实现可参考上述代码目录。

### **步骤一：定义Schema**

1. 定义开发人员实体Schema。

   **开发人员实体Schema**

   **重要**

   `id_generator` 是UModel建模中最关键的配置，决定了实体的唯一标识。

   ```
   metadata:
       description:
           en_us: Developer
           zh_cn: 研发人员
       display_name:
           en_us: Developer
           zh_cn: 研发人员
       domain: devops
       kind: entity_set
       name: devops.developer

   spec:
       id_generator: lower(to_hex(md5(cast(work_no as varbinary))))
       fields:
           - description:
               en_us: Work Number
               zh_cn: 工号
             display_name:
               en_us: Work Number
               zh_cn: 工号
             filterable: true
             name: work_no
             orderable: true
             short_description:
               en_us: Work Number
               zh_cn: 工号
             type: string
           - description:
               en_us: Developer Name
               zh_cn: 研发人员姓名
             display_name:
               en_us: Developer Name
               zh_cn: 研发人员姓名
             filterable: true
             name: name
             orderable: true
             short_description:
               en_us: Developer Name
               zh_cn: 研发人员姓名
             type: string
             ....
       name_fields:
           - name
           - work_no
           - email
           - team
           - role
       primary_key_fields:
           - work_no
       time_field: __time__
       type: entity_set
   ```
2. 定义管理关系Schema。

   **管理关系Schema**

   ```
   # EntitySetLink: manages
   metadata:
       description:
           en_us: |
               The link between "devops.developer" and "devops.code_repository".
           zh_cn: 研发人员-管理-代码仓库
       display_name:
           en_us: |
               Developer-Manages-Code-Repository
           zh_cn: 研发人员-管理-代码仓库
       domain: devops
       kind: entity_set_link
       name: devops.developer_manages_devops.code_repository
   # 关系的源和目标
   spec:
       dest:
           domain: devops
           kind: entity_set
           name: devops.code_repository
       entity_link_type: manages
       priority: 5
       src:
           domain: devops
           kind: entity_set
           name: devops.developer
   ```

### **步骤二：实现数据采集**

1. 从数据源获取开发人员实体原始数据，确定上传策略，并编写代码。

   * **数据源与采集方式**：从GitLab API采集。

     + 数据源：GitLab Members API。
     + 采集方式：遍历目标代码仓库，获取成员并去重。
   * **上传策略**：由于人员变动不频繁，即变化频率低；数据量约几百人，全量上传成本低；因此推荐策略为定时全量上传。

     + 执行频率：数据变化慢，每天一次即可。
     + KeepAlive：2天（172800秒），全量周期的2倍，防止任务失败。

     **开发人员实体数据采集代码示例**

     **说明**

     需要注意如下事项：

     + 使用字典去重，避免同一开发人员重复。
     + 记录日志便于调试和监控。
     + 处理API分页（如有需要）。
     + KeepAlive设为2天确保定时任务失败时数据仍可查询。

     ```
     import gitlab
     import schedule

     def fetch_developers():
         """从GitLab API获取开发人员"""
         # 初始化GitLab客户端
         client = gitlab.Gitlab(
             url=config['gitlab']['url'],
             private_token=config['gitlab']['access_token']
         )
         
         developers = {}  # 使用字典去重
         
         # 获取目标代码仓库
         project = client.projects.get(config['gitlab']['project_id'])

         # 获取成员并去重
         members = project.members_all.list(get_all=True)
         for member in members:
             user_id = str(member.id)
             if user_id not in developers:
                 developers[user_id] = {
                     'user_id': user_id,
                     'name': member.name,
                     'email': getattr(member, 'email', ''),
                     'role': str(member.access_level)
                 }
         
         logger.info(f"采集到{len(developers)}个开发人员")
         return list(developers.values())

     def sync_developers():
         """定时全量同步开发人员"""
         logger.info("开始同步开发人员...")
         
         # 1. 采集数据
         raw_developers = fetch_developers()
         
         # 2. 转换数据（步骤3详细说明）
         entities = convert_all_developers(raw_developers)
         
         # 3. 上传数据（步骤4详细说明）
         success = upload_entities(entities, workspace='o11y-workspace')
         
         if success:
             logger.info(f"成功上传{len(entities)}个开发人员实体")
         else:
             logger.error("上传失败")

     # 设置定时任务：每天凌晨3点执行
     schedule.every().day.at("03:00").do(sync_developers)
     ```
2. 从数据源获取管理关系实体原始数据，确定上传策略，并编写代码。

   * **数据源与采集方式**：获取开发人员管理代码仓库的关系。

     + 数据源：YAML配置文件，获取关系（开发人员——代码仓库）。
     + 采集方式：通过已有实体ID，关联静态配置。
   * **上传策略**：由于管理关系相对稳定，即变化频率低；数据来源为人工维护的静态配置文件；因此推荐策略为定时全量上传。

     + 执行频率：每小时一次，及时同步配置变更。
     + KeepAlive：2小时，全量周期的2倍，防止任务失败。

     **管理关系实体数据采集代码示例**

     配置文件示例：

     ```
     # 开发人员管理代码仓库映射
     manage_mappings:
       "1711055":  # 工号（developer的主键）
         repositories:
           - "mymall-order"      # 仓库名称（repository的标识）
           - "mymall-cart"
       
       "1703317":
         repositories:
           - "mymall-product"
           - "mymall-member"
           - "mymall-payment"
     ```

     实现代码：

     ```
     import yaml
     import schedule

     def generate_manage_relationships():
         """基于配置文件生成开发人员管理代码仓库的关系"""
         # 1. 加载配置文件
         with open('config/manage_mapping.yaml', 'r') as f:
             config = yaml.safe_load(f)
         
         # 2. 查询已有的实体（前提：实体已经上传到EntityStore）
         developers = query_entities_from_sls('devops.developer')
         repositories = query_entities_from_sls('devops.code_repository')
         
         # 3. 构建查找索引（通过主键快速查找）
         dev_map = {d['work_no']: d for d in developers}
         repo_map = {r['repo_name']: r for r in repositories}
         
         # 4. 生成关系数据

         relationships = [ ]

         for work_no, mapping in config['manage_mappings'].items():
             # 校验开发人员是否存在
             if work_no not in dev_map:
                 logger.warning(f"开发人员{work_no}不存在，跳过")
                 continue
             
             developer = dev_map[work_no]
             
             # 遍历该开发人员管理的所有仓库
             for repo_name in mapping['repositories']:
                 # 校验代码仓库是否存在
                 if repo_name not in repo_map:
                     logger.warning(f"代码仓库{repo_name}不存在，跳过")
                     continue
                 
                 repository = repo_map[repo_name]
                 
                 # 构建关系数据（保留原始标识，后续转换时使用）
                 relationships.append({
                     'src_entity_id': developer['__entity_id__'],
                     'dest_entity_id': repository['__entity_id__'],
                     'work_no': work_no,
                     'repo_name': repo_name
                 })
         
         logger.info(f"生成{len(relationships)}个管理关系")
         return relationships

     def sync_manage_relationships():
         """定时全量同步管理关系"""
         logger.info("开始同步管理关系...")
         
         # 1. 生成关系数据
         raw_relationships = generate_manage_relationships()
         
         # 2. 转换数据（步骤3详细说明）
         relationships = [convert_to_relationship(r) for r in raw_relationships]
         
         # 3. 上传数据（步骤4详细说明）
         success = upload_relationships(relationships, workspace='o11y-workspace')
         
         if success:
             logger.info(f"成功上传{len(relationships)}个管理关系")
         else:
             logger.error("上传失败")

     # 设置定时任务：每小时执行
     schedule.every().hour.do(sync_manage_relationships)
     ```

### **第三步：数据转换**

1. 编写代码，将原始数据转换为EntityStore格式。

   **开发人员实体数据转换**

   ```
   import hashlib
   import time

   def convert_developer_to_entity(raw_data):
       """将开发人员原始数据转换为实体格式"""
       # 1. 生成entity_id（根据Schema的id_generator规则）
       work_no = raw_data['user_id']
       entity_id = hashlib.md5(work_no.encode()).hexdigest()
       
       # 2. 构建实体数据
       entity = {
           # 系统必填字段
           '__domain__': 'devops',
           '__entity_type__': 'devops.developer',
           '__entity_id__': entity_id,
           '__method__': 'Update',  # 全量同步使用Update
           '__last_observed_time__': str(int(time.time())),
           '__keep_alive_seconds__': str(86400 * 2),  # 2天
           
           # 业务字段
           'work_no': work_no,
           'name': raw_data['name'],
           'email': raw_data['email'],
           'role': raw_data.get('role', 'developer')
       }
       
       return entity

   # 批量转换
   def convert_all_developers(raw_developers):
       """批量转换开发人员数据"""

       entities = [ ]

       for raw_data in raw_developers:
           try:
               entity = convert_developer_to_entity(raw_data)
               entities.append(entity)
           except Exception as e:
               logger.error(f"转换失败: {raw_data}, 错误: {e}")
       
       return entities
   ```

   **管理关系数据转换**

   ```
   def convert_to_relationship(rel_data):
       """将关系数据转换为标准格式"""
       return {
           # 关系系统字段
           '__src_domain__': 'devops',
           '__src_entity_type__': 'devops.developer',
           '__src_entity_id__': rel_data['src_entity_id'],
           '__dest_domain__': 'devops',
           '__dest_entity_type__': 'devops.code_repository',
           '__dest_entity_id__': rel_data['dest_entity_id'],
           '__link_type__': 'manages',
           '__method__': 'Update',
           '__last_observed_time__': str(int(time.time())),
           '__keep_alive_seconds__': str(7200),  # 2小时
           
           # 关系业务字段（可选）
           'work_no': rel_data.get('work_no'),
           'repo_name': rel_data.get('repo_name')
       }
   ```

### **第四步：上传数据**

1. 使用SLS SDK将数据上传到目标Logstore。

   **初始化SLS客户端**

   代码中参数获取方式参考如下：

   * accessKey与accessId获取参考[创建AccessKey](https://help.aliyun.com/zh/ram/user-guide/create-an-accesskey-pair)。
   * endpoint获取方式：

     1. 登录[日志服务控制台](https://sls.console.aliyun.com/?spm=a2c4g.11186623.0.0.70905a3dccueNa)，在Project列表中，单击目标Project。
     2. 单击Project名称右侧的![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/8576081671/p1020789.png)进入项目概览页面，在访问域名中复制公网域名。

   ```
   from aliyun.log import LogClient

   def init_sls_client():
       """初始化SLS客户端"""
       return LogClient(
           endpoint=config['sls']['endpoint'],
           accessKeyId=config['sls']['access_key_id'],
           accessKey=config['sls']['access_key_secret']
       )
   ```
2. 上传实体数据与关系数据。

   **重要**

   * 注意请通过批量上传提升性能，如每批次1000条。
   * 所有字段值必须转为字符串。
   * 添加异常处理和日志记录。

   **上传实体数据**

   ```
   from aliyun.log import PutLogsRequest, LogItem

   def upload_entities(entities, workspace):
       """批量上传实体数据到EntityStore"""
       client = init_sls_client()
       
       project = config['sls']['project']
       logstore = f"{workspace}__entity"
       
       # 分批上传（每批1000条）
       batch_size = 1000
       for i in range(0, len(entities), batch_size):
           batch = entities[i:i+batch_size]
           
           # 构建LogItem列表

           log_items = [ ]

           for entity in batch:
               log_item = LogItem()
               log_item.set_time(int(time.time()))
               log_item.set_contents([
                   (key, str(value)) for key, value in entity.items()
               ])
               log_items.append(log_item)
           
           # 上传
           try:
               request = PutLogsRequest(
                   project=project,
                   logstore=logstore,
                   topic="",
                   logitems=log_items
               )
               response = client.put_logs(request)
               logger.info(f"上传批次{i//batch_size + 1}成功")
           except Exception as e:
               logger.error(f"上传批次{i//batch_size + 1}失败: {e}")
               return False
       
       return True
   ```

   **上传关系数据**

   ```
   def upload_relationships(relationships, workspace):
       """批量上传关系数据到EntityStore"""
       client = init_sls_client()
       
       project = config['sls']['project']
       logstore = f"{workspace}__topo"  # 关系上传到__topo
       
       # 分批上传
       batch_size = 1000
       for i in range(0, len(relationships), batch_size):
           batch = relationships[i:i+batch_size]
           

           log_items = [ ]

           for rel in batch:
               log_item = LogItem()
               log_item.set_time(int(time.time()))
               log_item.set_contents([
                   (key, str(value)) for key, value in rel.items()
               ])
               log_items.append(log_item)
           
           try:
               request = PutLogsRequest(
                   project=project,
                   logstore=logstore,
                   topic="",
                   logitems=log_items
               )
               response = client.put_logs(request)
               logger.info(f"上传关系批次{i//batch_size + 1}成功")
           except Exception as e:
               logger.error(f"上传关系批次{i//batch_size + 1}失败: {e}")
               return False
       
       return True
   ```

## **相关参考**

### **推荐执行方式（Skill驱动）**

建议优先通过 skill 驱动方式完成执行与验证，脚本和查询语句作为底层实现与手动排查入口保留。

1. `verification-resource-readiness`
2. `verification-workspace-alignment`
3. `verification-workspace-refresh`
4. `verification-cms-visibility`
5. `verification-cms-field-check`
6. `verification-cms-sls-diagnose`

底层 refresh 入口为：

```bash
python3 devops_data_generator/main.py --mode single --config devops_data_generator/config
```

其中 `verification-workspace-refresh` 负责把数据真正写进 CMS workspace；如果没有先执行这一步，后续查询结果不具备验证意义。

### **其他实体的数据采集**

**说明**

以下列出的是DevOps场景Demo中涉及的实体类型，实际项目中请根据业务需求选择合适的实体，并调整数据源和采集方式。

DevOps场景包含多种实体，根据数据源不同采用不同的采集方式：

**DevOps实体（从GitLab API采集）**

|  |  |  |  |
| --- | --- | --- | --- |
| **实体类型** | **说明** | **数据源** | **采集方式** |
| `devops.code_repository` | 代码仓库 | GitLab API | 获取目标项目仓库信息 |
| `devops.code_release` | 代码发布 | GitLab API | 获取项目Tag或Release列表 |
| `devops.developer` | 开发人员 | GitLab API | 获取项目成员并去重 |

**容器镜像实体（从阿里云ACR采集）**

|  |  |  |  |
| --- | --- | --- | --- |
| **实体类型** | **说明** | **数据源** | **采集方式** |
| `devops.image_registry` | 镜像仓库 | ACR API | 列举镜像仓库列表 |
| `devops.image` | 容器镜像 | ACR API | 遍历仓库获取镜像标签 |

**K8s实体（从可观测监控CMS采集）**

|  |  |  |  |
| --- | --- | --- | --- |
| **实体类型** | **说明** | **数据源** | **采集方式** |
| `k8s.pod` | K8s Pod | CMS指标查询 | 查询Pod实体数据 |

### **其他关系的生成方式**

**说明**

以下列出的是DevOps场景Demo中涉及的关系类型，实际项目中请根据实体间的业务关联选择合适的关系类型，并配置相应的生成规则。

DevOps场景中的关系根据生成方式可分为**静态关系**和**动态关系**：

**静态关系（基于配置文件）**

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **关系类型** | **源实体** | **目标实体** | **配置方式** | **数据源** |
| `devops.developer manages devops.code_repository` | 开发人员 | 代码仓库 | YAML配置文件 | `manage_mapping.yaml` |
| `apm.service sourced_from devops.code_repository` | APM服务 | 代码仓库 | YAML配置文件 | `static_topo.yaml` |
| `apm.service sourced_from devops.code_release` | APM服务 | 代码发布 | 混合关系（静态+动态） | `static_topo.yaml` |
| `devops.developer manages apm.service` | 开发人员 | APM服务 | 混合关系（静态+动态） | `static_topo.yaml` |
| `devops.developer manages devops.image_registry` | 开发人员 | 镜像仓库 | 动态对动态 | `static_topo.yaml` |

**动态关系（基于数据关联）**

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **关系类型** | **源实体** | **目标实体** | **关联方式** | **匹配规则** |
| `devops.code_release sourced_from devops.code_repository` | 代码发布 | 代码仓库 | 字段匹配 | 通过repo_id关联 |
| `devops.image sourced_from devops.image_registry` | 容器镜像 | 镜像仓库 | 字段匹配 | 通过registry_id关联 |
| `devops.image sourced_from devops.code_release` | 容器镜像 | 代码发布 | Tag匹配 | 镜像Tag与发布Tag匹配 |
| `devops.image_registry contains devops.image` | 镜像仓库 | 容器镜像 | 字段匹配 | 通过registry_id关联 |
| `k8s.pod uses devops.image` | K8s Pod | 容器镜像 | 镜像名匹配 | Pod容器镜像与镜像实体匹配 |

### **实体与关系的上传策略参考**

**说明**

以下是DevOps场景Demo的上传策略配置示例，实际项目中需要根据数据变化频率、数据量大小、业务实时性要求等因素调整策略类型、执行频率和KeepAlive时间。

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **实体/关系** | **策略** | **频率** | **KeepAlive** | **数据源** |
| **devops.developer** | 定时全量 | 每天1次 | 2天 | GitLab API |
| **devops.code_repository** | 定时全量 | 1小时 | 2小时 | GitLab API |
| **devops.code_release** | 定时增量 | 5分钟 | 2小时 | GitLab API |
| **devops.image_registry** | 定时全量 | 1小时 | 2小时 | ACR API |
| **devops.image** | 定时增量 | 30分钟 | 2小时 | ACR API |
| **k8s.pod** | 实时查询 | 5 分钟 | 10 分钟 | K8S Server |
| **developer manages code_repository** | 定时全量 | 每小时 | 2小时 | 配置文件 |
| **code_release sourced_from code_repository** | 定时增量 | 5分钟 | 2小时 | 字段关联 |
| **image sourced_from image_registry** | 定时增量 | 30分钟 | 2小时 | 字段关联 |
| **image sourced_from code_release** | 定时增量 | 30分钟 | 2小时 | Tag匹配 |
| **image_registry contains image** | 定时增量 | 30分钟 | 2小时 | 字段关联 |
| **pod uses image** | 实时查询 | 5 分钟 | 10分钟 | 镜像名匹配 |
| **apm.service sourced_from code_repository** | 定时全量 | 4 小时 | 8 小时 | 配置文件 |
