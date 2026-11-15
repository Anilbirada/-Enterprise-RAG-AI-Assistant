import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import HTTPException
from app.api.deps import (
    get_current_settings,
    get_current_organization,
    get_current_active_user,
    get_current_tenant_id,
    require_role,
    require_permissions,
)
from app.core.config import get_settings
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.permissions import Permission, Role
from app.models.organization import Organization
from app.models.user import User


def test_get_current_settings_dep():
    settings = get_settings()
    assert get_current_settings(settings) == settings


def test_get_current_tenant_id():
    org_id = uuid.uuid4()
    mock_user = MagicMock(spec=User)
    mock_user.organization_id = org_id
    assert get_current_tenant_id(mock_user) == org_id


@pytest.mark.asyncio
async def test_get_current_active_user_active():
    user = MagicMock(spec=User)
    user.is_active = True
    active_user = await get_current_active_user(user)
    assert active_user == user


@pytest.mark.asyncio
async def test_get_current_active_user_inactive():
    user = MagicMock(spec=User)
    user.is_active = False
    with pytest.raises(UnauthorizedException) as exc_info:
        await get_current_active_user(user)
    assert "inactive" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_get_current_organization():
    org = MagicMock(spec=Organization)
    user = MagicMock(spec=User)
    user.organization = org
    res_org = await get_current_organization(user)
    assert res_org == org


@pytest.mark.asyncio
async def test_require_role_allowed():
    user = MagicMock(spec=User)
    user.role = Role.ORG_ADMIN.value
    user.is_active = True
    checker = require_role("ORG_ADMIN", "KNOWLEDGE_MANAGER")
    result = await checker(user)
    assert result == user


@pytest.mark.asyncio
async def test_require_role_super_admin_bypass():
    user = MagicMock(spec=User)
    user.role = Role.SUPER_ADMIN.value
    user.is_active = True
    checker = require_role("ORG_ADMIN")
    result = await checker(user)
    assert result == user


@pytest.mark.asyncio
async def test_require_role_forbidden():
    user = MagicMock(spec=User)
    user.role = Role.EMPLOYEE.value
    user.is_active = True
    checker = require_role("ORG_ADMIN")
    with pytest.raises(ForbiddenException) as exc_info:
        await checker(user)
    assert "Operation requires one of the following roles" in exc_info.value.message


@pytest.mark.asyncio
async def test_require_permissions_allowed():
    user = MagicMock(spec=User)
    user.role = Role.KNOWLEDGE_MANAGER.value
    user.is_active = True
    checker = require_permissions(Permission.UPLOAD_DOCUMENTS, Permission.VIEW_DOCUMENTS)
    result = await checker(user)
    assert result == user


@pytest.mark.asyncio
async def test_require_permissions_forbidden():
    user = MagicMock(spec=User)
    user.role = Role.EMPLOYEE.value
    user.is_active = True
    # EMPLOYEE does not have MANAGE_USERS
    checker = require_permissions(Permission.MANAGE_USERS)
    with pytest.raises(ForbiddenException) as exc_info:
        await checker(user)
    assert "Permission denied" in exc_info.value.message
