import json

def parse_pm2():
    with open('/root/portal-console/backend/data/pm2_jlist.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    parsed = []
    for item in data:
        name = item.get('name')
        if name == 'pm2-logrotate':
            continue
        
        pm2_env = item.get('pm2_env', {})
        cwd = pm2_env.get('pm2_cwd') or item.get('cwd')
        script = pm2_env.get('pm_exec_path')
        args = pm2_env.get('args', [])
        
        # Try to find PORT environment variable
        port = pm2_env.get('PORT') or pm2_env.get('env', {}).get('PORT')
        
        # Build standard pm2 commands
        start_cmd = f"pm2 start {script} --name \"{name}\""
        if args:
            if isinstance(args, list):
                args_str = " ".join(args)
            else:
                args_str = str(args)
            start_cmd += f" -- {args_str}"
            
        stop_cmd = f"pm2 stop {name}"
        restart_cmd = f"pm2 restart {name}"
        
        parsed.append({
            'name': name,
            'cwd': cwd,
            'script': script,
            'args': args,
            'port': port,
            'start_cmd': start_cmd,
            'stop_cmd': stop_cmd,
            'restart_cmd': restart_cmd
        })
        
    print(json.dumps(parsed, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    parse_pm2()
