import sys
sys.path.insert(0, '/app')

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.models.tenant import Tenant
from sqlalchemy import select
import uuid
from datetime import datetime, timezone

db = next(get_db())

user = db.execute(select(User).where(User.email == 'admin@docextract.com')).scalar_one_or_none()

if user:
    user.password_hash = hash_password('admin123')
    db.commit()
    print('Admin password updated.')
else:
    tenant = db.execute(select(Tenant)).scalar_one_or_none()
    if not tenant:
        tenant = Tenant(id=uuid.uuid4(), name='Default', created_at=datetime.now(timezone.utc))
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email='admin@docextract.com',
        password_hash=hash_password('admin123'),
        role='ADMIN',
        jwt_secret=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc)
    )
    db.add(user)
    db.commit()
    print('Admin user created.')
print('Done!')
