import sys
import os

# Adjust sys.path to find 'app'
sys.path.append('/app')

from app.db.session import SessionLocal
from app.models.project import Project
from app.models.project_link import ProjectLink
from app.models.server import Server
from app.models.enums import RuntimeType, ProjectLinkType, ProjectStatus, RuntimeStatus, OSType
from sqlalchemy import select

windows_services_data = [
    {
        "base_name": "arrowPuzzle",
        "deploy_path": "D:\\GitHub\\games\\arrowPuzzle",
        "start_cmd": "d: && cd D:\\GitHub\\games\\arrowPuzzle && python server.py",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8501).OwningProcess -Force",
        "port": 8501
    },
    {
        "base_name": "sliding-puzzle",
        "deploy_path": "D:\\GitHub\\games\\sliding-puzzle",
        "start_cmd": "d: && cd D:\\GitHub\\games\\sliding-puzzle && python server.py --host 0.0.0.0 --port 8502",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8502).OwningProcess -Force",
        "port": 8502
    },
    {
        "base_name": "puzzle-8x8",
        "deploy_path": "D:\\GitHub\\games\\puzzle-8x8",
        "start_cmd": "d: && cd D:\\GitHub\\games\\puzzle-8x8 && env PORT=8503 npm run start",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8503).OwningProcess -Force",
        "port": 8503
    },
    {
        "base_name": "puzzle_diamonds",
        "deploy_path": "D:\\GitHub\\games\\puzzle-diamonds\\python_app",
        "start_cmd": "d: && cd D:\\GitHub\\games\\puzzle-diamonds\\python_app && python server.py",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8504).OwningProcess -Force",
        "port": 8504
    },
    {
        "base_name": "shooter-game",
        "deploy_path": "D:\\GitHub\\games\\shooter-game",
        "start_cmd": "d: && cd D:\\GitHub\\games\\shooter-game && python server.py",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8505).OwningProcess -Force",
        "port": 8505
    },
    {
        "base_name": "snake-game",
        "deploy_path": "D:\\GitHub\\games\\snake-game",
        "start_cmd": "d: && cd D:\\GitHub\\games\\snake-game && npm run preview -- --host 0.0.0.0 --port 8506",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8506).OwningProcess -Force",
        "port": 8506
    },
    {
        "base_name": "thetower-idletower",
        "deploy_path": "D:\\GitHub\\games\\thetower-idletower",
        "start_cmd": "d: && cd D:\\GitHub\\games\\thetower-idletower && python start_server.py",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8507).OwningProcess -Force",
        "port": 8507
    },
    {
        "base_name": "tower-game",
        "deploy_path": "D:\\GitHub\\games\\tower-game",
        "start_cmd": "d: && cd D:\\GitHub\\games\\tower-game && python -m http.server 8508 --bind 0.0.0.0",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8508).OwningProcess -Force",
        "port": 8508
    },
    {
        "base_name": "sliding-puzzle-porn",
        "deploy_path": "D:\\GitHub\\games\\sliding-puzzle-porn",
        "start_cmd": "d: && cd D:\\GitHub\\games\\sliding-puzzle-porn && python server.py --host 0.0.0.0 --port 8552",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8552).OwningProcess -Force",
        "port": 8552
    },
    {
        "base_name": "gameportal",
        "deploy_path": "D:\\GitHub\\games\\portal",
        "start_cmd": "d: && cd D:\\GitHub\\games\\portal && python app.py --host 0.0.0.0 --port 80",
        "stop_cmd": "Stop-Process -Id (Get-NetTCPConnection -LocalPort 80).OwningProcess -Force",
        "port": 80
    }
]

def restore_windows():
    session = SessionLocal()
    try:
        # Fetch Server ID 8 (i9-4090)
        server = session.get(Server, 8)
        if not server:
            print("Error: Server with ID 8 (i9-4090) was not found in database!")
            return
            
        # Update server to Windows
        server.os_type = OSType.WINDOWS
        session.flush()
        print(f"Updated Server '{server.name}' os_type to '{server.os_type}' successfully.")
        
        for item in windows_services_data:
            name = f"{item['base_name']}-win"
            
            # Check if project already exists
            existing_project = session.scalars(select(Project).where(Project.name == name)).first()
            if existing_project:
                print(f"Project '{name}' already exists. Skipping insertion.")
                continue
            
            # Create Windows Project
            project = Project(
                name=name,
                description=f"Windows local dev instance for {item['base_name']}",
                tags=["game", "windows", "dev"],
                deploy_path=item["deploy_path"],
                runtime_type=RuntimeType.CMD, # CMD or PYTHON_SCRIPT is valid for Windows command execution
                start_cmd=item["start_cmd"],
                stop_cmd=item["stop_cmd"],
                restart_cmd=f"{item['stop_cmd']}; {item['start_cmd']}",
                is_favorite=False,
                current_status=ProjectStatus.UNKNOWN,
                runtime_status=RuntimeStatus.UNKNOWN,
                server_id=8
            )
            session.add(project)
            session.flush() # Populate project ID
            
            # Create Localhost Link
            port = item["port"]
            url = f"http://localhost" if port == 80 else f"http://localhost:{port}"
            
            link = ProjectLink(
                project_id=project.id,
                link_type=ProjectLinkType.WEB,
                title="Local Dev Web",
                url=url,
                sort_order=1
            )
            session.add(link)
            print(f"Created Windows Project: {name} (URL: {url}, Path: {item['deploy_path']})")
            
        session.commit()
        print("Windows local dev data restoration completed successfully!")
    except Exception as e:
        session.rollback()
        print(f"Error during Windows restoration: {e}")
    finally:
        session.close()

if __name__ == '__main__':
    restore_windows()
