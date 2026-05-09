# 完成重复待办

一个零依赖的本地待办应用，核心功能是类似截图里的“完成重复”：

- 任务可设置日期、时间。
- 重复模式支持“不重复”“完成重复”“固定日程重复”。
- “完成重复”会在勾选完成时，以完成当天为起点计算下一次日期，例如每 27 天。
- “固定日程重复”会以当前到期日为起点计算下一次日期。
- 数据保存在浏览器 `localStorage`。

## 使用

直接用浏览器打开 `index.html` 即可：

```text
todoist/index.html
```

首次打开会内置几条“手机卡保号提醒”示例任务，其中“美国Talkatone”默认设置为每 27 天完成重复。

## 后端提醒

浏览器提醒可以直接使用。微信、飞书、邮件、webhook 需要启动本地后端：

```powershell
cd D:\GitHub\kits\todoist
python server.py
```

然后打开：

```text
http://127.0.0.1:8765/
```

支持的通道：

- 企业微信机器人：填写完整 webhook，或只填写机器人 key。
- 飞书机器人：填写 webhook；如果机器人启用了签名校验，再填写 secret。
- 通用 webhook：POST JSON，包含 `text` 和 `task`。
- 邮件：SMTP SSL 端口默认用 465，其他端口会走 STARTTLS。

后端状态和配置保存在 `todoist/data/state.json`，该目录为运行时生成。

## Portal SSO

Todoist 已按 `D:\GitHub\games\portal` 的子项目协议接入：

- Portal 跳转地址：`http://127.0.0.1:8765/sso/portal?token=...&lang=zh`
- Todoist 验证 HS256 JWT，要求 `iss=portal`、`exp` 未过期、`jti` 未重复使用。
- 登录成功后写入 `todoist_session` HttpOnly cookie。
- `/api/session` 返回当前 portal 用户。
- `/api/load` 和 `/api/sync` 会按 `portal:<user_id>` 隔离任务数据、提醒设置和已发送提醒记录。
- 每个 portal 用户都有自己的通知路径：飞书、企业微信、邮件、通用 webhook 都存放在该用户自己的 `settings` 下。
- 新 portal 用户不会继承 `global` 的提醒设置，必须单独配置自己的提醒通道。
- 未通过 portal 登录时仍使用 `global` 数据，兼容原来的本地模式。

本地 SSO 配置：

```text
todoist/config
```

`PORTAL_SSO_SECRET` 必须与 portal 数据库 `apps.sso_secret` 中 `slug=todoist` 的记录一致。`todoist/config` 已加入 `.gitignore`，不要提交真实密钥。

## 现成项目调研

通知底座优先推荐 Apprise：

- 它是开源 Python 通知库，同时提供 CLI 和自托管 API 网关。
- 官方文档显示支持 Feishu/Lark、WeCom Bot、邮件和 webhook/URL 类通知。
- 当前 `server.py` 先用标准库直接实现这些核心通道，避免安装依赖；后续如果通知通道继续增加，可以把 `send_all()` 替换为 Apprise URL 列表。

## 滴答清单功能参考

当前版本按 TickTick/滴答清单的公开功能做了第一批核心结构：

- 任务列表、今天、最近 7 天、收集箱、已完成。
- 任务详情：日期、时间、完成重复、优先级、标签、备注、子任务。
- 多视图：列表、两周日历、按日期状态分组的看板、四象限、25 分钟专注计时。
- 提醒：浏览器提醒、飞书、企业微信、邮件、通用 webhook。

仍未做完整的功能：自然语言识别、时间线/Gantt、习惯打卡统计、多人协作、附件/Markdown、桌面小组件、跨设备账号同步。
