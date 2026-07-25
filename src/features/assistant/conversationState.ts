export interface PendingAssistantMessage {
  conversationId: string;
  question: string;
  clientMessageId: string;
}

export function getPendingAssistantMessage(
  pending: PendingAssistantMessage | null,
  conversationId: string,
  question: string,
  createId: () => string
): PendingAssistantMessage {
  if (pending?.conversationId === conversationId && pending.question === question) return pending;
  return { conversationId, question, clientMessageId: createId() };
}
