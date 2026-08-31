import os
import sys

# Add backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables for testing
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.schemas.server import ServerCreate
from app.api.routes.servers import create_server

def test():
    db = SessionLocal()
    # Initialize DB (creates tables)
    init_db(db, "admin", "admin123")
    
    # Let's get the admin user
    from app.models.user import User
    from sqlalchemy import select
    admin = db.scalar(select(User).where(User.username == "admin"))
    
    payload = ServerCreate(
        name="test-windows-server",
        host="192.168.1.100",
        os_type="windows",
        ssh_port=8008,
        ssh_username=None,
        ssh_auth_type="ssh_key",
        ssh_key_id=None,
        env_type="public",
        description="A Windows Server test",
        tags=["win", "test"]
    )
    
    try:
        server = create_server(payload=payload, _=admin, db=db)
        print("Success! Created server:", server)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
