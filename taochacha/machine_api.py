from fastapi import FastAPI
import uvicorn
import subprocess

app = FastAPI()

@app.get("/execute")
def execute(command: str):
    # 使用subprocess.run执行命令
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    # 输出命令的执行结果
    if result.returncode == 0:
        return result.stdout
    return "Fail:" + result.stderr


if __name__ == "__main__":
    uvicorn.run("machine_api:app", host="0.0.0.0", port=10001, reload=True)

# pip install fastapi
# pip install uvicorn
# pm2 start machine_api.py --interpreter python3
