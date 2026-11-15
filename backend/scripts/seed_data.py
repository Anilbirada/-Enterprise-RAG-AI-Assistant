import asyncio
import uuid
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.department import Department
from app.models.user import User
from app.core.security import get_password_hash


from sqlalchemy import select

async def seed():
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        result = await session.execute(select(User).filter_by(email="admin@acme.com"))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            print("[INFO] Seed data already exists in database. Skipping seed step.")
            return

        # Create Organization
        org = Organization(
            id=uuid.uuid4(),
            name="Acme Corporation",
            slug="acme-corp",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        # Create Departments
        dept_eng = Department(
            id=uuid.uuid4(),
            organization_id=org.id,
            name="Engineering",
            code="ENG",
        )
        dept_hr = Department(
            id=uuid.uuid4(),
            organization_id=org.id,
            name="Human Resources",
            code="HR",
        )
        session.add_all([dept_eng, dept_hr])
        await session.flush()

        password_hash = get_password_hash("Password123!")

        # Create Users
        admin_user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            department_id=dept_eng.id,
            email="admin@acme.com",
            hashed_password=password_hash,
            full_name="Alice Admin",
            role="ORG_ADMIN",
            is_active=True,
        )

        km_user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            department_id=dept_eng.id,
            email="km@acme.com",
            hashed_password=password_hash,
            full_name="Kevin Manager",
            role="KNOWLEDGE_MANAGER",
            is_active=True,
        )

        emp_user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            department_id=dept_hr.id,
            email="employee@acme.com",
            hashed_password=password_hash,
            full_name="Emily Employee",
            role="EMPLOYEE",
            is_active=True,
        )

        session.add_all([admin_user, km_user, emp_user])
        await session.commit()

        print("[SUCCESS] Seeded default database with:")
        print(f"  Organization: Acme Corporation (Slug: {org.slug})")
        print("  Users:")
        print("    1. Admin:             admin@acme.com    / Password123! (Role: ORG_ADMIN)")
        print("    2. Knowledge Manager: km@acme.com       / Password123! (Role: KNOWLEDGE_MANAGER)")
        print("    3. Employee:          employee@acme.com / Password123! (Role: EMPLOYEE)")


if __name__ == "__main__":
    asyncio.run(seed())
