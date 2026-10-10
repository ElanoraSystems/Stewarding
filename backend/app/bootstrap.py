import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Employee, EmployeeLocation, Location, User
from .permissions import MANAGER
from .security import hash_password
from .seed import ensure_lookups, sync_roles

MIN_PASSWORD = 12


def create_manager(db: Session, email: str, password: str, name: str, code: str) -> Employee:
    """Creates the first real Back of House Manager without any demo data."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters")
    email = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) or db.scalar(select(Employee.id).where(Employee.employee_code == code)):
        raise ValueError("A user with that email or employee ID already exists")
    roles = sync_roles(db)
    ensure_lookups(db)
    user = User(email=email, password_hash=hash_password(password), role_id=roles[MANAGER].id)
    db.add(user)
    db.flush()
    employee = Employee(employee_code=code, user_id=user.id, full_name=name, job_title="Back of House Manager", email=email)
    employee.locations = [EmployeeLocation(location_id=loc_id) for loc_id in db.scalars(select(Location.id))]
    db.add(employee)
    db.commit()
    return employee


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first Back of House Manager account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--code", required=True, help="employee ID")
    args = parser.parse_args()
    password = os.environ.get("STW_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
    if "STW_BOOTSTRAP_PASSWORD" not in os.environ and password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match")
    try:
        with SessionLocal() as db:
            create_manager(db, args.email, password, args.name, args.code)
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"Created manager {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
