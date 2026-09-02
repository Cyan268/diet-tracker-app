from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssistantConversation, AssistantMessage
from app.schemas.assistant import (
    AssistantAnswerResponse,
    AssistantContextMessage,
)


class ConversationNotFoundError(ValueError):
    pass


class ConversationAppendConflictError(ValueError):
    pass


async def create_conversation(
    session: AsyncSession,
    user_id: UUID,
    title: str | None,
) -> AssistantConversation:
    conversation = AssistantConversation(
        user_id=user_id,
        title=title.strip() if title else "新对话",
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def list_conversations(
    session: AsyncSession,
    user_id: UUID,
    limit: int,
) -> list[tuple[AssistantConversation, int]]:
    result = await session.execute(
        select(AssistantConversation, func.count(AssistantMessage.id))
        .outerjoin(
            AssistantMessage,
            AssistantMessage.conversation_id == AssistantConversation.id,
        )
        .where(AssistantConversation.user_id == user_id)
        .group_by(AssistantConversation.id)
        .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id.desc())
        .limit(limit)
    )
    return [(conversation, int(count)) for conversation, count in result.all()]


async def get_conversation(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> AssistantConversation | None:
    return await session.scalar(
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
    )


async def list_messages(
    session: AsyncSession,
    conversation_id: UUID,
    limit: int = 100,
) -> list[AssistantMessage]:
    messages = list(
        await session.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation_id)
            .order_by(AssistantMessage.sequence.desc())
            .limit(limit)
        )
    )
    messages.reverse()
    return messages


async def count_messages(session: AsyncSession, conversation_id: UUID) -> int:
    count = await session.scalar(
        select(func.count(AssistantMessage.id)).where(
            AssistantMessage.conversation_id == conversation_id
        )
    )
    return int(count or 0)


async def delete_conversation(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
) -> bool:
    conversation = await get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return False
    await session.execute(
        delete(AssistantMessage).where(AssistantMessage.conversation_id == conversation_id)
    )
    await session.delete(conversation)
    await session.commit()
    return True


async def get_completed_turn_by_client_id(
    session: AsyncSession,
    conversation_id: UUID,
    client_message_id: UUID,
) -> tuple[AssistantMessage, AssistantMessage] | None:
    user_message = await session.scalar(
        select(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.client_message_id == client_message_id,
            AssistantMessage.role == "user",
        )
    )
    if user_message is None:
        return None
    assistant_message = await session.scalar(
        select(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation_id,
            AssistantMessage.sequence == user_message.sequence + 1,
            AssistantMessage.role == "assistant",
        )
    )
    if assistant_message is None:
        raise ConversationAppendConflictError("message is still incomplete")
    return user_message, assistant_message


async def load_conversation_context(
    session: AsyncSession,
    conversation_id: UUID,
    *,
    max_messages: int = 8,
    max_characters: int = 6000,
) -> list[AssistantContextMessage]:
    recent = list(
        await session.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation_id)
            .order_by(AssistantMessage.sequence.desc())
            .limit(max_messages)
        )
    )
    selected: list[AssistantMessage] = []
    characters = 0
    for message in recent:
        length = len(message.content)
        if selected and characters + length > max_characters:
            break
        selected.append(message)
        characters += length
    selected.reverse()
    while selected and selected[0].role != "user":
        selected.pop(0)
    return [
        AssistantContextMessage(
            role=message.role,
            content=message.content,
            reference_date=message.reference_date,
        )
        for message in selected
    ]


async def append_conversation_turn(
    session: AsyncSession,
    user_id: UUID,
    conversation_id: UUID,
    client_message_id: UUID,
    question: str,
    reference_date: date,
    answer: AssistantAnswerResponse,
) -> tuple[AssistantMessage, AssistantMessage, bool]:
    conversation = await session.scalar(
        select(AssistantConversation)
        .where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
        .with_for_update()
    )
    if conversation is None:
        raise ConversationNotFoundError
    replay = await get_completed_turn_by_client_id(
        session,
        conversation_id,
        client_message_id,
    )
    if replay is not None:
        if replay[0].content != question.strip() or replay[0].reference_date != reference_date:
            raise ConversationAppendConflictError(
                "client message id was already used with different content"
            )
        return replay[0], replay[1], True

    last_sequence = await session.scalar(
        select(func.coalesce(func.max(AssistantMessage.sequence), 0)).where(
            AssistantMessage.conversation_id == conversation_id
        )
    )
    user_message = AssistantMessage(
        conversation_id=conversation_id,
        client_message_id=client_message_id,
        role="user",
        content=question.strip(),
        sequence=int(last_sequence or 0) + 1,
        reference_date=reference_date,
        evidence=[],
        warnings=[],
    )
    assistant_message = AssistantMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=answer.answer,
        sequence=user_message.sequence + 1,
        provider=answer.provider,
        model=answer.model,
        prompt_version=answer.prompt_version,
        fallback_used=answer.fallback_used,
        latency_ms=answer.latency_ms,
        input_tokens=answer.usage.input_tokens,
        output_tokens=answer.usage.output_tokens,
        trace_id=answer.trace_id,
        evidence=[item.model_dump(mode="json") for item in answer.evidence],
        warnings=answer.warnings,
        disclaimer=answer.disclaimer,
    )
    if conversation.title == "新对话" and int(last_sequence or 0) == 0:
        conversation.title = question.strip()[:30]
    conversation.updated_at = datetime.now(UTC)
    session.add_all([user_message, assistant_message])
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        replay = await get_completed_turn_by_client_id(
            session,
            conversation_id,
            client_message_id,
        )
        if replay is None:
            raise ConversationAppendConflictError("concurrent message append conflict") from error
        if replay[0].content != question.strip() or replay[0].reference_date != reference_date:
            raise ConversationAppendConflictError(
                "client message id was already used with different content"
            ) from error
        return replay[0], replay[1], True
    await session.refresh(user_message)
    await session.refresh(assistant_message)
    return user_message, assistant_message, False
