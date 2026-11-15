from enum import Enum
from typing import Dict, Set


class Role(str, Enum):
    """System and Tenant-level Roles."""
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    KNOWLEDGE_MANAGER = "KNOWLEDGE_MANAGER"
    EMPLOYEE = "EMPLOYEE"


class Permission(str, Enum):
    """Granular system actions."""
    MANAGE_ORGANIZATION = "organization:manage"
    MANAGE_USERS = "users:manage"
    MANAGE_DEPARTMENTS = "departments:manage"
    MANAGE_DOCUMENTS = "documents:manage"
    UPLOAD_DOCUMENTS = "documents:upload"
    VIEW_DOCUMENTS = "documents:view"
    CHAT_QUERY = "chat:query"
    VIEW_ANALYTICS = "analytics:view"
    SUBMIT_FEEDBACK = "feedback:submit"


# Role-Permission Mapping Matrix
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.SUPER_ADMIN: {
        Permission.MANAGE_ORGANIZATION,
        Permission.MANAGE_USERS,
        Permission.MANAGE_DEPARTMENTS,
        Permission.MANAGE_DOCUMENTS,
        Permission.UPLOAD_DOCUMENTS,
        Permission.VIEW_DOCUMENTS,
        Permission.CHAT_QUERY,
        Permission.VIEW_ANALYTICS,
        Permission.SUBMIT_FEEDBACK,
    },
    Role.ORG_ADMIN: {
        Permission.MANAGE_USERS,
        Permission.MANAGE_DEPARTMENTS,
        Permission.MANAGE_DOCUMENTS,
        Permission.UPLOAD_DOCUMENTS,
        Permission.VIEW_DOCUMENTS,
        Permission.CHAT_QUERY,
        Permission.VIEW_ANALYTICS,
        Permission.SUBMIT_FEEDBACK,
    },
    Role.KNOWLEDGE_MANAGER: {
        Permission.MANAGE_DOCUMENTS,
        Permission.UPLOAD_DOCUMENTS,
        Permission.VIEW_DOCUMENTS,
        Permission.CHAT_QUERY,
        Permission.SUBMIT_FEEDBACK,
    },
    Role.EMPLOYEE: {
        Permission.VIEW_DOCUMENTS,
        Permission.CHAT_QUERY,
        Permission.SUBMIT_FEEDBACK,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    """Checks whether a given role holds the requested permission."""
    try:
        enum_role = Role(role)
        return permission in ROLE_PERMISSIONS.get(enum_role, set())
    except ValueError:
        return False
