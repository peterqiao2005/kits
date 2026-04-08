from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_db, require_admin
from app.models.server import Server
from app.models.ssh_key import SSHKey
from app.schemas.server import ServerCreate, ServerRead, ServerUpdate
from app.schemas.ssh_key import SSHKeySummaryRead
from app.services.secrets import encrypt_secret

router = APIRouter(prefix="/servers", tags=["servers"])


def build_server_read(server: Server) -> ServerRead:
    return ServerRead(
        id=server.id,
        name=server.name,
        host=server.host,
        ssh_port=server.ssh_port,
        ssh_username=server.ssh_username,
        ssh_auth_type=server.ssh_auth_type,
        ssh_key_id=server.ssh_key_id,
        env_type=server.env_type,
        description=server.description,
        tags=server.tags or [],
        has_ssh_password=bool(server.ssh_password_encrypted),
        ssh_key=SSHKeySummaryRead.model_validate(server.ssh_key) if server.ssh_key else None,
        created_at=server.created_at,
        updated_at=server.updated_at,
        project_count=len(server.projects),
    )


def validate_ssh_key(db: Session, ssh_key_id: int | None) -> SSHKey | None:
    if ssh_key_id is None:
        return None
    ssh_key = db.get(SSHKey, ssh_key_id)
    if ssh_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="SSH key not found."
        )
    return ssh_key


def apply_auth_settings(
    server: Server,
    *,
    ssh_password: str | None,
    db: Session,
) -> None:
    if not server.ssh_username or not server.ssh_username.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSH username is required.",
        )
    server.ssh_username = server.ssh_username.strip()

    if server.ssh_auth_type.value == "password":
        if ssh_password is not None:
            if not ssh_password.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SSH password cannot be empty.",
                )
            server.ssh_password_encrypted = encrypt_secret(ssh_password.strip())
        if not server.ssh_password_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SSH password is required for password authentication.",
            )
        server.ssh_key_id = None
        return

    validate_ssh_key(db, server.ssh_key_id)
    if server.ssh_key_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an SSH key for key-based authentication.",
        )
    server.ssh_password_encrypted = None


@router.get("", response_model=list[ServerRead])
def list_servers(
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ServerRead]:
    servers = db.scalars(
        select(Server)
        .options(selectinload(Server.projects), selectinload(Server.ssh_key))
        .order_by(Server.name)
    ).all()
    return [build_server_read(server) for server in servers]


@router.post("", response_model=ServerRead, status_code=status.HTTP_201_CREATED)
def create_server(
    payload: ServerCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ServerRead:
    server = Server(**payload.model_dump(exclude={"ssh_password"}))
    apply_auth_settings(server, ssh_password=payload.ssh_password, db=db)
    db.add(server)
    db.commit()
    db.refresh(server)
    return build_server_read(server)


@router.put("/{server_id}", response_model=ServerRead)
def update_server(
    server_id: int,
    payload: ServerUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ServerRead:
    server = db.scalar(
        select(Server)
        .where(Server.id == server_id)
        .options(selectinload(Server.projects), selectinload(Server.ssh_key))
    )
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found."
        )

    updates = payload.model_dump(exclude_unset=True)
    ssh_password = updates.pop("ssh_password", None)
    for field, value in updates.items():
        setattr(server, field, value)

    apply_auth_settings(server, ssh_password=ssh_password, db=db)
    db.commit()
    db.refresh(server)
    return build_server_read(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(
    server_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found."
        )
    db.delete(server)
    db.commit()
