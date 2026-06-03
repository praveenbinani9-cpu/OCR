from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Tenant(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    rate_limit: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all,delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all,delete-orphan")
    api_keys = relationship("APIKey", back_populates="tenant", cascade="all,delete-orphan")
