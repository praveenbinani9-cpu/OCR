"""CLI: bootstrap a tenant + admin user + initial API key.

Usage:
    python -m app.scripts.bootstrap_tenant \\
        --name "Acme Corp" --email admin@acme.com --password "ChangeMe!123"
"""
from __future__ import annotations

import argparse
import sys

from app.core.database import db_session
from app.core.security import (
    generate_api_key,
    hash_api_key,
    hash_password,
)
from app.models.api_key import APIKey
from app.models.tenant import Tenant
from app.models.user import User, UserRole


def bootstrap(name: str, email: str, password: str, plan: str = "free", rate_limit: int = 60) -> None:
    with db_session() as db:
        api_key_plain = generate_api_key()
        tenant = Tenant(
            name=name,
            api_key_hash=hash_api_key(api_key_plain),
            plan=plan,
            rate_limit=rate_limit,
        )
        db.add(tenant)
        db.flush()

        import secrets

        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            jwt_secret=secrets.token_urlsafe(32),
        )
        db.add(user)

        key = APIKey(
            tenant_id=tenant.id,
            key_hash=hash_api_key(api_key_plain),
            name="bootstrap",
            rate_limit_per_minute=rate_limit,
        )
        db.add(key)
        db.commit()

        print("==== Tenant bootstrap complete ====")
        print(f"tenant_id: {tenant.id}")
        print(f"admin_email: {email}")
        print(f"api_key: {api_key_plain}   <-- SHOWN ONLY ONCE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--plan", default="free")
    parser.add_argument("--rate-limit", type=int, default=60)
    args = parser.parse_args()
    bootstrap(args.name, args.email, args.password, args.plan, args.rate_limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
