import sys
import os

# Adjust sys.path to find 'app'
sys.path.append('/app')

from app.db.session import SessionLocal
from app.models.project import Project
from app.models.project_link import ProjectLink
from app.models.server import Server
from app.models.enums import RuntimeType, ProjectLinkType, ProjectStatus, RuntimeStatus
from sqlalchemy import select

services_data = [
    {
        "name": "arrowPuzzle",
        "deploy_path": "/root/games/arrowPuzzle",
        "start_cmd": "cd /root/games/arrowPuzzle && pm2 start /usr/bin/python3 --name \"arrowPuzzle\" -- server.py",
        "stop_cmd": "pm2 stop arrowPuzzle",
        "restart_cmd": "pm2 restart arrowPuzzle",
        "port": 8501
    },
    {
        "name": "sliding-puzzle",
        "deploy_path": "/root/games/sliding-puzzle",
        "start_cmd": "cd /root/games/sliding-puzzle && pm2 start /usr/bin/python3 --name \"sliding-puzzle\" -- server.py --host 0.0.0.0 --port 8502",
        "stop_cmd": "pm2 stop sliding-puzzle",
        "restart_cmd": "pm2 restart sliding-puzzle",
        "port": 8502
    },
    {
        "name": "puzzle-8x8",
        "deploy_path": "/root/games/puzzle-8x8",
        "start_cmd": "cd /root/games/puzzle-8x8 && PORT=8503 pm2 start /root/.nvm/versions/node/v20.20.2/bin/npm --name \"puzzle-8x8\" -- run start",
        "stop_cmd": "pm2 stop puzzle-8x8",
        "restart_cmd": "pm2 restart puzzle-8x8",
        "port": 8503
    },
    {
        "name": "puzzle_diamonds",
        "deploy_path": "/root/games/puzzle-diamonds/python_app",
        "start_cmd": "cd /root/games/puzzle-diamonds/python_app && pm2 start /usr/bin/python3 --name \"puzzle_diamonds\" -- server.py",
        "stop_cmd": "pm2 stop puzzle_diamonds",
        "restart_cmd": "pm2 restart puzzle_diamonds",
        "port": 8504
    },
    {
        "name": "shooter-game",
        "deploy_path": "/root/games/shooter-game",
        "start_cmd": "cd /root/games/shooter-game && pm2 start /usr/bin/python3 --name \"shooter-game\" -- server.py",
        "stop_cmd": "pm2 stop shooter-game",
        "restart_cmd": "pm2 restart shooter-game",
        "port": 8505
    },
    {
        "name": "snake-game",
        "deploy_path": "/root/games/snake-game",
        "start_cmd": "cd /root/games/snake-game && pm2 start /root/.nvm/versions/node/v20.20.2/bin/npm --name \"snake-game\" -- run preview -- --host 0.0.0.0 --port 8506",
        "stop_cmd": "pm2 stop snake-game",
        "restart_cmd": "pm2 restart snake-game",
        "port": 8506
    },
    {
        "name": "thetower-idletower",
        "deploy_path": "/root/games/thetower-idletower",
        "start_cmd": "cd /root/games/thetower-idletower && pm2 start /usr/bin/python3 --name \"thetower-idletower\" -- start_server.py",
        "stop_cmd": "pm2 stop thetower-idletower",
        "restart_cmd": "pm2 restart thetower-idletower",
        "port": 8507
    },
    {
        "name": "tower-game",
        "deploy_path": "/root/games/tower-game",
        "start_cmd": "cd /root/games/tower-game && pm2 start /usr/bin/python3 --name \"tower-game\" -- -m http.server 8508 --bind 0.0.0.0",
        "stop_cmd": "pm2 stop tower-game",
        "restart_cmd": "pm2 restart tower-game",
        "port": 8508
    },
    {
        "name": "sliding-puzzle-porn",
        "deploy_path": "/root/games/sliding-puzzle-porn",
        "start_cmd": "cd /root/games/sliding-puzzle-porn && pm2 start /usr/bin/python3 --name \"sliding-puzzle-porn\" -- server.py --host 0.0.0.0 --port 8552",
        "stop_cmd": "pm2 stop sliding-puzzle-porn",
        "restart_cmd": "pm2 restart sliding-puzzle-porn",
        "port": 8552
    },
    {
        "name": "gameportal",
        "deploy_path": "/root/games/portal",
        "start_cmd": "cd /root/games/portal && pm2 start /usr/bin/python3 --name \"gameportal\" -- app.py --host 0.0.0.0 --port 80",
        "stop_cmd": "pm2 stop gameportal",
        "restart_cmd": "pm2 restart gameportal",
        "port": 80
    }
]

def restore():
    session = SessionLocal()
    try:
        # Verify if Server ID 7 exists
        server = session.get(Server, 7)
        if not server:
            print("Error: Server with ID 7 (webgame.8833.space) was not found in database!")
            return
        
        print(f"Found Server: {server.name} ({server.host})")
        
        for item in services_data:
            name = item["name"]
            # Check if project already exists
            existing_project = session.scalars(select(Project).where(Project.name == name)).first()
            
            if existing_project:
                print(f"Project '{name}' already exists. Skipping insertion.")
                continue
            
            # Create Project
            project = Project(
                name=name,
                description=f"PM2 hosted service: {name}",
                tags=["game", "pm2"],
                deploy_path=item["deploy_path"],
                runtime_type=RuntimeType.PM2_PROCESS,
                start_cmd=item["start_cmd"],
                stop_cmd=item["stop_cmd"],
                restart_cmd=item["restart_cmd"],
                is_favorite=False,
                current_status=ProjectStatus.UNKNOWN,
                runtime_status=RuntimeStatus.UNKNOWN,
                server_id=7
            )
            session.add(project)
            session.flush() # Populate project ID
            
            # Create Web Link
            port = item["port"]
            url = f"http://webgame.8833.space" if port == 80 else f"http://webgame.8833.space:{port}"
            
            link = ProjectLink(
                project_id=project.id,
                link_type=ProjectLinkType.WEB,
                title="Demo Web",
                url=url,
                sort_order=1
            )
            session.add(link)
            print(f"Created Project: {name} (URL: {url}, Cwd: {item['deploy_path']})")
            
        session.commit()
        print("Data restoration completed successfully!")
    except Exception as e:
        session.rollback()
        print(f"Error during restoration: {e}")
    finally:
        session.close()

if __name__ == '__main__':
    restore()
