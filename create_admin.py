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

load_dotenv()

from database import SessionLocal, Base, engine
from models import User
from services.security import hash_password

Base.metadata.create_all(bind=engine)


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Administrator account.")
    parser.add_argument("--uname", help="Administrator username")
    parser.add_argument("--email", help="Administrator email address")
    parser.add_argument("--password", help="Administrator password")
    parser.add_argument("--phone", help="Contact phone number (optional)", default=None)

    args = parser.parse_args()

    uname = args.uname or input("Enter administrator username (uname): ").strip()
    email = args.email or input("Enter administrator email: ").strip()
    password = args.password or input("Enter administrator password: ").strip()

    if not uname or not email or not password:
        print("ERROR: uname, email, and password are required!")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(
            (User.uname == uname) | (User.email == email.lower())
        ).first()

        if existing:
            print(f"User '{uname}' / '{email}' already exists. Elevating permissions to Administrator...")
            existing.is_admin = True
            db.commit()
            print("Successfully granted ADMINISTRATOR privileges.")
            return

        admin_user = User(
            uname=uname,
            email=email.lower(),
            hashed_password=hash_password(password),
            dzial="Management",
            nrtel=args.phone,
            is_admin=True
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("--------------------------------------------------")
        print(f" Success! Administrator '{admin_user.uname}' created.")
        print(f" Email: {admin_user.email}")
        print(" Role: Administrator (is_admin=True)")
        print(" You can now log in and generate invite codes.")
        print("--------------------------------------------------")
    finally:
        db.close()


if __name__ == "__main__":
    main()
