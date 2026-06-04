
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.core.database import get_db
from app.models.document import Document
from app.models.extraction import Extraction
from app.schemas.document import DocumentOut, DocumentPage
from app.schemas.extraction import ExtractionResponse, ValidationResult
from app.services.validation import normalize_extraction

router = APIRouter()


@router.get("", response_model=DocumentPage)
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
) -> DocumentPage:
    stmt = select(Document).where(Document.tenant_id == principal.tenant_id)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return DocumentPage(
        items=[
            DocumentOut(
                id=str(d.id),
                filename=d.filename,
                file_size=d.file_size,
                mime_type=d.mime_type,
                status=d.status.value if hasattr(d.status, "value") else str(d.status),
                created_at=d.created_at,
            )
            for d in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=ExtractionResponse)
def get_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ExtractionResponse:
    doc = db.get(Document, document_id)
    if not doc or doc.tenant_id != principal.tenant_id:
        raise HTTPException(404, "document_not_found")
    extraction = db.execute(
        select(Extraction).where(Extraction.document_id == doc.id)
    ).scalar_one_or_none()
    if not extraction:
        # Document exists but extraction not yet produced
        return ExtractionResponse(
            status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            document_id=str(doc.id),
            document_type="UNKNOWN",
            overall_confidence=0.0,
            processing_time_ms=0,
            data=normalize_extraction({}),
            validation=ValidationResult(),
            review_required=False,
        )
    data_node = (extraction.extracted_json or {}).get("data", {})
    validation = ValidationResult.model_validate(extraction.validation_result or {})
    return ExtractionResponse(
        status="success",
        document_id=str(doc.id),
        document_type=extraction.document_type,
        overall_confidence=extraction.overall_confidence,
        processing_time_ms=extraction.processing_time_ms,
        data=normalize_extraction(data_node),
        validation=validation,
        review_required=any(
            [
                not validation.amounts_reconciled,
                not validation.gstin_valid,
                validation.duplicate_detected,
            ]
        ),
    )
