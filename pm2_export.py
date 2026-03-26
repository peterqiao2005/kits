#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
import os
from pathlib import Path

OUT_FILE = "ecosystem.config.js"

def run_pm2_jlist():
    try:
        r = subprocess.run(
            ["pm2", "jlist"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return json.loads(r.stdout)
    except Exception as e:
        print("failed to run pm2 jlist:", e, file=sys.stderr)
        sys.exit(1)

def relpath_if_possible(path, base):
    try:
        return "./" + os.path.relpath(path, base)
    except Exception:
        return path

def export_apps(pm2_list, names, export_all=False):
    apps = []

    for p in pm2_list:
        env = p.get("pm2_env", {})
        name = env.get("name")

        if not name:
            continue

        # 非 all 模式：只导出指定 name
        if not export_all and name not in names:
            continue

        cwd = env.get("pm_cwd")
        script = env.get("pm_exec_path")
        interpreter = env.get("exec_interpreter")

        app = {
            "name": name,
            "cwd": "__dirname",
            "autorestart": True,
            "max_restarts": 10,
            "restart_delay": 2000,
        }

        if script:
            app["script"] = (
                relpath_if_possible(script, cwd) if cwd else script
            )

        if interpreter and interpreter != "none":
            app["interpreter"] = (
                relpath_if_possible(interpreter, cwd) if cwd else interpreter
            )

        # args
        args = env.get("args")
        if isinstance(args, str) and args.strip():
            app["args"] = args.strip()
        elif isinstance(args, list) and args:
            app["args"] = " ".join(str(x) for x in args)

        # env（清理 pm2 内部变量）
        raw_env = env.get("env", {})
        clean_env = {}
        for k, v in raw_env.items():
            if k.startswith("PM2_") or k.startswith("pm2_"):
                continue
            if isinstance(v, (str, int, float, bool)):
                clean_env[k] = str(v)
        if clean_env:
            app["env"] = clean_env

        apps.append(app)

    return apps

def write_ecosystem(apps):
    data = {"apps": apps}
    txt = json.dumps(data, indent=2, ensure_ascii=False)
    # "__dirname" 需要是 JS 标识符
    txt = txt.replace('"cwd": "__dirname"', '"cwd": __dirname')
    Path(OUT_FILE).write_text(
        "module.exports = " + txt + ";\n",
        encoding="utf-8"
    )

def main():
    if len(sys.argv) < 2:
        print(
            "usage: pm2_export.py <pm2_name1> [pm2_name2 ...] | all",
            file=sys.stderr,
        )
        sys.exit(2)

    args = sys.argv[1:]

    export_all = False
    names = set()

    if len(args) == 1 and args[0] == "all":
        export_all = True
    else:
        names = set(args)

    pm2_list = run_pm2_jlist()
    apps = export_apps(pm2_list, names, export_all=export_all)

    if not apps:
        if export_all:
            print("no pm2 process found", file=sys.stderr)
        else:
            print(
                "no pm2 process matched: " + ", ".join(names),
                file=sys.stderr,
            )
        sys.exit(3)

    write_ecosystem(apps)

    print(f"exported {len(apps)} app(s) to {OUT_FILE}")

if __name__ == "__main__":
    main()
