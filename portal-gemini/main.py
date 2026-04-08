import json
import logging
import os
import subprocess

import paramiko
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# 配置日志记录到控制台
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")


def load_projects():
    try:
        with open("projects.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"无法读取配置文件: {e}")
        return []


def execute_ssh(project, command):
    host = project["host"]
    user = project["user"]
    port = str(project.get("port", 22))
    key_path = project.get("key_file")

    log_prefix = f"[{project['name']} @ {host}]"
    logger.info(f"{log_prefix} 准备通过系统 SSH 执行: {command}")

    # 构建系统 SSH 命令
    # -i: 指定私钥
    # -p: 指定端口
    # -o StrictHostKeyChecking=no: 自动接受新主机的 key，防止卡住
    # -o BatchMode=yes: 非交互模式，如果需要密码直接报错而不是卡住等待输入
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "BatchMode=yes",
        "-p",
        port,
        f"{user}@{host}",
        command,
    ]

    # 如果指定了私钥文件，加入 -i 参数
    if key_path:
        # 处理 Windows 路径中的空格或特殊字符
        if os.path.exists(key_path):
            ssh_cmd.insert(1, "-i")
            ssh_cmd.insert(2, key_path)
        else:
            return f"错误: 私钥文件不存在 -> {key_path}"

    try:
        # 执行命令并捕获输出
        # shell=True 在 Windows 上有助于处理复杂的路径，但要注意安全
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0:
            logger.info(f"{log_prefix} 执行成功")
            return result.stdout if result.stdout else "Success"
        else:
            logger.error(f"{log_prefix} 执行失败: {result.stderr}")
            return f"SSH Error (Code {result.returncode}): {result.stderr}"

    except subprocess.TimeoutExpired:
        return "Error: SSH 连接超时"
    except Exception as e:
        return f"系统调用错误: {str(e)}"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        projects = load_projects()
        return templates.TemplateResponse(
            request=request, name="index.html", context={"projects": projects}
        )
    except Exception as e:
        logger.error(f"渲染模板失败: {e}")
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(f"渲染出错: {str(e)}")


@app.post("/action")
async def action(project_id: int = Form(...), mode: str = Form(...)):
    projects = load_projects()
    project = next((p for p in projects if p["id"] == project_id), None)

    if not project:
        return JSONResponse({"status": "error", "output": "未找到该项目配置"})

    cmd = project["start_cmd"] if mode == "start" else project["stop_cmd"]

    # 核心：执行命令并捕获日志
    output = execute_ssh(project, cmd)

    return JSONResponse(
        {"status": "done", "project": project["name"], "mode": mode, "output": output}
    )


if __name__ == "__main__":
    import uvicorn

    # 启动时打印当前配置
    logger.info("服务启动中，请访问 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=18000)
