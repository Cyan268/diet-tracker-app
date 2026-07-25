import { getPendingAssistantMessage } from "../src/features/assistant/conversationState";

describe("assistant conversation retry state", () => {
  test("reuses the id for the same message after an uncertain network result", () => {
    const pending = {
      conversationId: "conversation-1",
      question: "我今天吃得怎么样？",
      clientMessageId: "message-1",
    };

    expect(
      getPendingAssistantMessage(pending, "conversation-1", "我今天吃得怎么样？", () => "new")
    ).toBe(pending);
  });

  test("creates a new id when the conversation or content changes", () => {
    const pending = {
      conversationId: "conversation-1",
      question: "问题一",
      clientMessageId: "message-1",
    };

    expect(
      getPendingAssistantMessage(pending, "conversation-1", "问题二", () => "message-2")
    ).toEqual({
      conversationId: "conversation-1",
      question: "问题二",
      clientMessageId: "message-2",
    });
  });
});
