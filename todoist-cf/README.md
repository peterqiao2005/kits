# Todoist CF

Cloudflare Worker + D1 版本，不覆盖 `todoist/` 本地版本。

## 架构

- 前端：Worker 直接返回静态 HTML/CSS/JS。
- API：同一个 Worker 提供 `/api/*`。
- 数据：Cloudflare D1，按 `portal:<user_id>` 隔离。
- 登录：兼容 `D:\GitHub\games\portal` 的 SSO JWT。
- 提醒：Worker Cron 每分钟扫描所有用户任务，并按各用户自己的通知设置发送。

## 多用户

portal 登录后，Worker 使用 `portal:<sub>` 作为用户数据键。每个用户独立保存：

- 任务列表
- 完成记录和重复规则
- 提醒设置
- 飞书、企业微信、邮件、webhook 路径
- 已发送提醒记录

未登录访问会返回 401，不提供匿名全局数据。

## 部署

当前本机没有全局 Node，但已经可使用现有便携 Node。PowerShell 里先运行：

```powershell
$env:PATH='D:\GitHub\WebAI2API-MC\.tools\node-v24.15.0-win-x64;' + $env:PATH
```

1. 安装依赖：

```powershell
cd D:\GitHub\kits\todoist-cf
npm install
```

2. 创建 D1 数据库：

```powershell
npx wrangler d1 create todoist_cf
```

把返回的 `database_id` 填到 `wrangler.toml`。

3. 初始化表：

```powershell
npm run db:init
```

4. 配置 secrets：

```powershell
npx wrangler secret put PORTAL_SSO_SECRET
npx wrangler secret put SESSION_SECRET
npx wrangler secret put RESEND_API_KEY
```

`PORTAL_SSO_SECRET` 必须与 portal 中 `slug=todoist-cf` 或对应应用记录的 `sso_secret` 一致。

5. 部署：

```powershell
npm run deploy
```

6. portal 应用配置：

```text
base_url=https://你的-worker域名
sso_secret=同 PORTAL_SSO_SECRET
```

portal 会跳转到：

```text
https://你的-worker域名/sso/portal?token=...&lang=zh
```

也可以用脚本直接注册到本地 portal SQLite：

```powershell
python .\tools\register_portal_app.py `
  --base-url https://你的-worker域名 `
  --sso-secret 你的PORTAL_SSO_SECRET
```

## Cloudflare 控制台界面部署

如果不用命令行，控制台里可以这样操作：

1. 进入 Cloudflare Dashboard。
2. 打开 Workers & Pages。
3. 选择 Create application。
4. 选择 Workers。
5. 选择导入 Git 仓库，或创建 Worker 后在在线编辑器粘贴 `src/worker.js`。
6. 打开 Worker 的 Settings。
7. 在 Variables and Secrets 里添加：
   - `PORTAL_SSO_SECRET`
   - `SESSION_SECRET`
   - `RESEND_API_KEY`，可选
8. 在 D1 里创建数据库 `todoist_cf`。
9. 在 D1 控制台执行 `schema.sql`。
10. 回到 Worker Settings，添加 D1 binding：
    - Variable name: `DB`
    - D1 database: `todoist_cf`
11. 在 Triggers 里添加 Cron Trigger：
    - `*/1 * * * *`
12. 部署后，把 Worker 域名填进 portal 的应用 `base_url`。

更推荐命令行部署，因为 `wrangler.toml`、D1 binding 和 cron 都能随项目一起管理，后续改动更可追踪。

## 邮件提醒

Cloudflare Workers 不能直接使用 SMTP。CF 版本的邮件提醒使用 Resend HTTP API：

- 全局 `RESEND_API_KEY` 可放在 Worker secret。
- 也可以在每个用户的通知设置里填写自己的 Resend API Key。

飞书、企业微信和通用 webhook 使用 HTTPS fetch 直接发送。
