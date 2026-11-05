"""Research assistant endpoints: ask a question, read the workspace's chat history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.database.models import Conversation, Message
from app.services.document_service import get_document

router = APIRouter(prefix="/documents", tags=["assistant"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    insufficient_evidence: bool
    general_explanation: str | None = Field(
        description="General background, NOT taken from the paper (labelled separately)."
    )
    citations: list[dict[str, Any]]


class HistoryMessage(BaseModel):
    role: str
    content: str
    citations: list[dict[str, Any]]
    insufficient_evidence: bool
    created_at: datetime


class HistoryResponse(BaseModel):
    document_id: str
    conversation_id: int | None
    messages: list[HistoryMessage]


@router.post("/{document_id}/chat", response_model=ChatResponse)
def chat(
    document_id: str, body: ChatRequest, request: Request, session: Session = Depends(get_session)
) -> ChatResponse:
    result = request.app.state.research_assistant.ask(
        session, document_id, body.question.strip(), body.conversation_id
    )
    return ChatResponse(
        conversation_id=result.conversation_id,
        answer=result.answer,
        insufficient_evidence=result.insufficient_evidence,
        general_explanation=result.general_explanation,
        citations=result.citations,
    )


@router.get("/{document_id}/chat/history", response_model=HistoryResponse)
def chat_history(document_id: str, session: Session = Depends(get_session)) -> HistoryResponse:
    get_document(session, document_id)
    conversation = session.scalar(
        select(Conversation)
        .where(Conversation.document_id == document_id)
        .order_by(Conversation.id.desc())
        .limit(1)
    )
    messages: list[Message] = list(conversation.messages) if conversation else []
    return HistoryResponse(
        document_id=document_id,
        conversation_id=conversation.id if conversation else None,
        messages=[
            HistoryMessage(
                role=m.role,
                content=m.content,
                citations=m.citations_json or [],
                insufficient_evidence=m.insufficient_evidence,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
