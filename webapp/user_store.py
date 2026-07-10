"""
User accounts for AqarIQ, stored as (:User) nodes in the same Neo4j graph --
no separate database needed, consistent with how DatasetVersion already
lives in the graph. Passwords are bcrypt-hashed, never stored in plain text.
"""

from typing import Optional

import bcrypt

from neo4j_client import run_read, run_write


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_user(email: str) -> Optional[dict]:
    rows = run_read(
        """
        MATCH (u:User {email: toLower($email)})
        RETURN u.email AS email, u.name AS name, u.password_hash AS password_hash,
               u.role AS role, u.active AS active,
               u.total_messages AS total_messages,
               toString(u.last_active_at) AS last_active_at,
               toString(u.created_at) AS created_at
        """,
        email=email,
    )
    return rows[0] if rows else None


def create_user(email: str, name: str, password: str, role: str = "rep") -> dict:
    rows = run_write(
        """
        CREATE (u:User {
            email: toLower($email),
            name: $name,
            password_hash: $password_hash,
            role: $role,
            active: true,
            total_messages: 0,
            last_active_at: null,
            created_at: datetime()
        })
        RETURN u.email AS email, u.name AS name, u.role AS role
        """,
        email=email,
        name=name,
        password_hash=hash_password(password),
        role=role,
    )
    return rows[0]


def list_users() -> list:
    return run_read(
        """
        MATCH (u:User)
        RETURN u.email AS email, u.name AS name, u.role AS role, u.active AS active,
               u.total_messages AS total_messages,
               toString(u.last_active_at) AS last_active_at,
               toString(u.created_at) AS created_at
        ORDER BY u.created_at DESC
        """
    )


def set_active(email: str, active: bool) -> None:
    run_write(
        "MATCH (u:User {email: toLower($email)}) SET u.active = $active",
        email=email,
        active=active,
    )


def record_activity(email: str) -> None:
    run_write(
        """
        MATCH (u:User {email: toLower($email)})
        SET u.total_messages = coalesce(u.total_messages, 0) + 1,
            u.last_active_at = datetime()
        """,
        email=email,
    )
