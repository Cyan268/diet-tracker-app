from uuid import UUID, uuid4

from httpx2 import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AiCallLog, AssistantMessage
from app.repositories.assistant_conversations import load_conversation_context


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_conversation(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        "/api/v1/ai/assistant/conversations",
        headers=headers,
        json={},
    )
    assert response.status_code == 201
    return response.json()


async def send_message(
    client: AsyncClient,
    headers: dict[str, str],
    conversation_id: str,
    question: str,
    client_message_id: str,
):
    return await client.post(
        f"/api/v1/ai/assistant/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "client_message_id": client_message_id,
            "question": question,
            "reference_date": "2026-07-20",
            "locale": "zh-CN",
        },
    )


async def test_conversation_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/ai/assistant/conversations")

    assert response.status_code == 401


async def test_conversation_persists_ordered_turns_and_idempotent_replay(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await register(api_client, "conversation-owner@example.com")
    conversation = await create_conversation(api_client, headers)
    conversation_id = conversation["id"]

    first_id = str(uuid4())
    first = await send_message(
        api_client,
        headers,
        conversation_id,
        "我今天吃得怎么样？",
        first_id,
    )
    assert first.status_code == 200
    assert first.json()["replayed"] is False

    second_id = str(uuid4())
    second = await send_message(
        api_client,
        headers,
        conversation_id,
        "那最近七天呢？",
        second_id,
    )
    assert second.status_code == 200
    detail = second.json()["conversation"]
    assert detail["title"] == "我今天吃得怎么样？"
    assert detail["message_count"] == 4
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message["sequence"] for message in detail["messages"]] == [1, 2, 3, 4]
    assert detail["messages"][1]["evidence"][0]["tool_name"] == "get_today_summary"
    assert detail["messages"][3]["evidence"][0]["tool_name"] == "get_weekly_trend"

    replay = await send_message(
        api_client,
        headers,
        conversation_id,
        "那最近七天呢？",
        second_id,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["conversation"]["message_count"] == 4

    conflict = await send_message(
        api_client,
        headers,
        conversation_id,
        "相同幂等键不能代表另一条消息",
        second_id,
    )
    assert conflict.status_code == 409

    listing = await api_client.get(
        "/api/v1/ai/assistant/conversations",
        headers=headers,
    )
    assert listing.status_code == 200
    assert listing.json()[0]["message_count"] == 4

    async with session_factory() as session:
        call_count = await session.scalar(
            select(func.count(AiCallLog.id)).where(AiCallLog.operation == "assistant_conversation")
        )
    assert call_count == 2


async def test_conversation_is_user_scoped_and_delete_removes_messages(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = await register(api_client, "conversation-private@example.com")
    other = await register(api_client, "conversation-intruder@example.com")
    conversation = await create_conversation(api_client, owner)
    conversation_id = conversation["id"]
    response = await send_message(
        api_client,
        owner,
        conversation_id,
        "我今天吃得怎么样？",
        str(uuid4()),
    )
    assert response.status_code == 200

    assert (
        await api_client.get(
            f"/api/v1/ai/assistant/conversations/{conversation_id}",
            headers=other,
        )
    ).status_code == 404
    assert (
        await send_message(
            api_client,
            other,
            conversation_id,
            "尝试越权",
            str(uuid4()),
        )
    ).status_code == 404
    assert (
        await api_client.delete(
            f"/api/v1/ai/assistant/conversations/{conversation_id}",
            headers=other,
        )
    ).status_code == 404

    deleted = await api_client.delete(
        f"/api/v1/ai/assistant/conversations/{conversation_id}",
        headers=owner,
    )
    assert deleted.status_code == 204
    async with session_factory() as session:
        remaining = await session.scalar(
            select(func.count(AssistantMessage.id)).where(
                AssistantMessage.conversation_id == UUID(conversation_id)
            )
        )
    assert remaining == 0


async def test_conversation_context_keeps_only_four_latest_turns(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = await register(api_client, "conversation-context@example.com")
    conversation = await create_conversation(api_client, headers)
    conversation_id = conversation["id"]
    for turn in range(1, 6):
        response = await send_message(
            api_client,
            headers,
            conversation_id,
            f"第{turn}轮今天怎么样？",
            str(uuid4()),
        )
        assert response.status_code == 200

    async with session_factory() as session:
        context = await load_conversation_context(session, UUID(conversation_id))

    assert len(context) == 8
    assert context[0].role == "user"
    assert context[0].content == "第2轮今天怎么样？"
    assert context[-1].role == "assistant"
