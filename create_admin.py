#!/usr/bin/env python3
"""
CLI script to bootstrap or promote an Administrator account.
Usage locally or in Railway container:
    python create_admin.py
Or with arguments:
    python create_admin.py --uname admin --email admin@company.com --password SuperSecret123!
"""
import sys
import argparse
from dotenv import load_dotenv
from sqlalchemy import func
from sqlalchemy.orm import Session

load_dotenv()

from database import SessionLocal, Base, engine
from models import User
from services.people_service import ensure_person_for_user
from services.security import hash_password

Base.metadata.create_all(bind=engine)


def create_or_promote_admin(
    db: Session,
    uname: str,
    email: str,
    password: str,
    phone: str | None = None,
) -> tuple[User, str]:
    """Create a new admin or promote an existing user matched by uname or email, and sync People."""
    clean_uname = uname.strip()
    clean_email = email.strip().lower()
    clean_phone = (phone or "").strip() or None

    by_uname = db.query(User).filter(User.uname == clean_uname).first()
    by_email = db.query(User).filter(func.lower(User.email) == clean_email).first()

    if by_uname and by_email and by_uname.id != by_email.id:
        raise ValueError(
            f"Conflict: username '{clean_uname}' belongs to user id={by_uname.id} "
            f"({by_uname.email}), while email '{clean_email}' belongs to user id={by_email.id} "
            f"({by_email.uname})."
        )

    existing = by_uname or by_email
    if existing:
        was_admin = bool(existing.is_admin)
        existing.is_admin = True
        if not existing.dzial:
            existing.dzial = "Management"
        if clean_phone and not existing.nrtel:
            existing.nrtel = clean_phone
        ensure_person_for_user(
            db,
            name=existing.uname,
            team=existing.dzial,
            email=existing.email,
            phone=existing.nrtel,
        )
        db.commit()
        db.refresh(existing)
        status = "already_admin" if was_admin else "promoted"
        return existing, status

    admin_user = User(
        uname=clean_uname,
        email=clean_email,
        hashed_password=hash_password(password),
        dzial="Management",
        nrtel=clean_phone,
        is_admin=True,
    )
    db.add(admin_user)
    ensure_person_for_user(
        db,
        name=admin_user.uname,
        team=admin_user.dzial,
        email=admin_user.email,
        phone=admin_user.nrtel,
    )
    db.commit()
    db.refresh(admin_user)
    return admin_user, "created"


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Administrator account.")
    parser.add_argument("--uname", help="Administrator username")
    parser.add_argument("--email", help="Administrator email address")
    parser.add_argument("--password", help="Administrator password")
    parser.add_argument("--phone", help="Contact phone number (optional)", default=None)

    args = parser.parse_args()

    uname = (args.uname or input("Enter administrator username (uname): ")).strip()
    email = (args.email or input("Enter administrator email: ")).strip().lower()
    password = (args.password or input("Enter administrator password: ")).strip()

    if not uname or not email or not password:
        print("ERROR: uname, email, and password are required!")
        sys.exit(1)

    db = SessionLocal()
    try:
        try:
            admin_user, status = create_or_promote_admin(
                db, uname=uname, email=email, password=password, phone=args.phone
            )
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)

        if status == "already_admin":
            print(
                f"User '{admin_user.uname}' ({admin_user.email}) is already an Administrator. "
                "Verified Management team and People roster entry."
            )
            return

        if status == "promoted":
            print(
                f"User '{admin_user.uname}' ({admin_user.email}) already exists. "
                "Elevated permissions to Administrator and synced People roster."
            )
            return

        print("--------------------------------------------------")
        print(f" Success! Administrator '{admin_user.uname}' created.")
        print(f" Email: {admin_user.email}")
        print(" Role: Administrator (is_admin=True)")
        print(" Team: Management (synced to People roster)")
        print(" You can now log in and generate invite codes.")
        print("--------------------------------------------------")
    finally:
        db.close()


if __name__ == "__main__":
    main()
