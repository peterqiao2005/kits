# 项目设计文档

## 一、项目目标

开发一套个人使用的轻量项目入口面板，用于统一查看和管理分布在多台服务器、本机、局域网设备上的各类服务与项目。

系统重点不是企业级资产管理，而是：

- 方便查看常用项目
- 统一保存访问入口和说明
- 查看项目当前是否在线
- 触发项目的启动、停止、重启
- 尽量避免在自定义系统中直接保存 SSH 私钥或密码

## 二、总体架构

### 1. 自定义门户（本项目）

职责：

- 项目信息展示
- 项目入口聚合
- 状态展示
- 调用执行层进行 `start / stop / restart`
- 展示最近操作记录

### 2. 执行层（外部现成工具）

优先方案：`Rundeck`

职责：

- 管理节点（服务器）
- 安全保存 SSH 凭据
- 执行远程命令
- 提供 Job / API 给门户调用

### 3. 监控层（外部现成工具）

优先方案：`Uptime Kuma`

职责：

- HTTP / TCP / Ping / Docker 状态监控
- 可选通知
- 向门户提供状态参考

## 三、功能范围

### 1. 项目管理

支持录入和编辑以下信息：

- 项目名称
- 简介
- 标签
- GitHub 地址
- Web 访问地址
- 管理后台地址
- 文档地址
- 所属服务器
- 部署路径
- 运行方式
- 启动说明
- 停止说明
- 备注

运行方式枚举建议：

- `docker_compose`
- `docker_container`
- `systemd_service`
- `pm2_process`
- `python_script`
- `shell_script`
- `custom`

### 2. 项目状态展示

门户首页需要展示：

- 项目是否在线
- 最后一次检测时间
- 所属服务器
- 当前是否可访问
- 是否配置了启动 / 停止能力

状态来源优先级建议：

1. `Uptime Kuma API` 状态
2. 若未配置 Kuma，则显示 `unknown`
3. 后续可扩展轻量主动探测

状态值建议：

- `online`
- `offline`
- `degraded`
- `unknown`

### 3. 项目操作

在项目详情页提供按钮：

- 启动
- 停止
- 重启

按钮动作不直接执行 SSH，而是：

1. 调用门户后端
2. 门户后端调用 Rundeck Job API
3. Rundeck 在目标节点上执行预定义命令

这样自定义系统不直接接触 SSH 私钥。

### 4. 快捷入口

每个项目支持多个入口：

- Web
- Admin
- GitHub
- Docs
- SSH
- Monitor
- Logs

前端展示为链接按钮。

### 5. 搜索与筛选

支持按以下维度筛选：

- 项目名
- 标签
- 所属服务器
- 状态
- 运行方式

### 6. 操作记录

记录以下内容：

- 操作时间
- 项目名
- 操作类型（`start / stop / restart`）
- 触发人
- 执行结果
- Rundeck execution id
- 简短返回信息

## 四、非功能要求

### 1. 安全要求

- 自定义门户不保存服务器 SSH 私钥、密码
- 所有远程命令执行通过 Rundeck 完成
- 门户仅保存 Rundeck API Token
- 门户与 Rundeck、Kuma 间通信走内网或 VPN
- 门户本身需要登录认证
- 需要基础 RBAC，至少区分：
  - `admin`
  - `viewer`

### 2. 易用性

首页打开后可快速看到：

- 哪些项目在线
- 哪些项目离线
- 点一下能进入哪里
- 能不能启停

### 3. 维护性

- 项目配置应尽量结构化，不要把重要信息只写在大段备注里
- 支持后续扩展更多执行层或监控层

## 五、建议技术栈

你是个人使用、追求实用，我建议别搞太复杂：

### 后端

- FastAPI
- SQLAlchemy
- PostgreSQL
- `httpx`（调用 Rundeck / Kuma API）
- Alembic

### 前端

- Vue 3
- Element Plus

### 部署

- Docker Compose

## 六、数据库设计建议

### 1. `users`

- `id`
- `username`
- `password_hash`
- `role`
- `created_at`

### 2. `servers`

- `id`
- `name`
- `host`
- `env_type`（`public / lan / local`）
- `description`
- `tags`
- `created_at`
- `updated_at`

### 3. `projects`

- `id`
- `name`
- `description`
- `tags`
- `repo_url`
- `server_id`
- `deploy_path`
- `runtime_type`
- `start_note`
- `stop_note`
- `access_note`
- `rundeck_job_start_id`
- `rundeck_job_stop_id`
- `rundeck_job_restart_id`
- `kuma_monitor_id`
- `is_favorite`
- `created_at`
- `updated_at`

### 4. `project_links`

- `id`
- `project_id`
- `link_type`
- `title`
- `url`
- `sort_order`

### 5. `operation_logs`

- `id`
- `project_id`
- `user_id`
- `action`
- `status`
- `message`
- `external_execution_id`
- `created_at`

## 七、API 设计建议

### 认证

- `POST /api/auth/login`
- `GET /api/auth/me`

### 服务器

- `GET /api/servers`
- `POST /api/servers`
- `PUT /api/servers/{id}`
- `DELETE /api/servers/{id}`

### 项目

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{id}`
- `PUT /api/projects/{id}`
- `DELETE /api/projects/{id}`

### 项目状态

- `GET /api/projects/{id}/status`
- `POST /api/projects/sync-status`

### 项目操作

- `POST /api/projects/{id}/start`
- `POST /api/projects/{id}/stop`
- `POST /api/projects/{id}/restart`

### 链接

- `POST /api/projects/{id}/links`
- `PUT /api/project-links/{id}`
- `DELETE /api/project-links/{id}`

### 日志

- `GET /api/operation-logs`

## 八、前端页面设计

### 1. 首页 Dashboard

展示卡片或表格：

- 项目名
- 当前状态
- 所属服务器
- 标签
- 常用入口
- 操作按钮

支持：

- 搜索
- 收藏
- 仅看在线
- 按服务器筛选

### 2. 项目详情页

展示：

- 基本信息
- 各类入口链接
- 启停说明
- 当前状态
- 最近操作记录

### 3. 服务器页

展示：

- 每台服务器关联的项目
- 在线 / 离线统计

### 4. 操作记录页

展示：

- 时间
- 项目
- 操作
- 结果

### 5. 设置页

展示：

- Rundeck 配置
- Kuma 配置
- 用户管理

## 九、与 Rundeck 的集成方式

### 推荐模式

每个项目可绑定 3 个 Rundeck Job：

- `start job`
- `stop job`
- `restart job`

门户点击按钮时：

1. 查到项目绑定的 Job ID
2. 调用 Rundeck API 触发执行
3. 记录 execution id
4. 轮询执行结果
5. 更新操作日志
6. 可选地延迟刷新 Kuma 状态

这样做的优点：

- 自定义门户不处理 SSH
- 命令执行逻辑放在 Rundeck
- 项目启停逻辑更灵活
- 某些项目可以只配置 `start`，不配置 `stop`

## 十、与 Uptime Kuma 的集成方式

每个项目可选绑定一个 `monitor`。

门户中：

- 列表页显示 Kuma 状态
- 详情页显示最近状态时间
- 点击可跳转到 Kuma 对应页面

若未绑定 `monitor`：

- 状态显示 `unknown`
