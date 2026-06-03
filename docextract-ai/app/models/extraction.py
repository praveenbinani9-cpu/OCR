from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GUID, JSONType, TimestampMixin, UUIDPKMixin


class Extraction(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "extractions"
    __table_args__ = (
        Index(
            "ix_extractions_dup",
            "tenant_id",
            "document_number",
            "vendor_gstin",
            "document_date",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    validation_result: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Denormalized for duplicate detection index
    document_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vendor_gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_date: Mapped[str | None] = mapped_column(String(20), nullable=True)

    document = relationship("Document", back_populates="extraction")
