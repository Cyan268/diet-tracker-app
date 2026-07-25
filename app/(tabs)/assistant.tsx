import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { v4 as uuidv4 } from "uuid";

import type {
  AssistantConversationDetailResponse,
  AssistantConversationMessageResponse,
  AssistantConversationSummaryResponse,
  AssistantConversationTurnResponse,
} from "@/api/types";
import { getAssistantMessageProviderLabel, getToolLabel } from "@/features/assistant/presentation";
import {
  getPendingAssistantMessage,
  type PendingAssistantMessage,
} from "@/features/assistant/conversationState";
import { useAuth } from "@/features/auth/AuthContext";
import { getToday } from "@/utils/date";

const SUGGESTIONS = ["我今天吃得怎么样？", "那最近七天趋势呢？", "查询燕麦片的营养"];

export default function AssistantScreen() {
  const { apiRequest, status } = useAuth();
  const [conversations, setConversations] = useState<AssistantConversationSummaryResponse[]>([]);
  const [activeConversation, setActiveConversation] =
    useState<AssistantConversationDetailResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const pendingMessageRef = useRef<PendingAssistantMessage | null>(null);

  const fetchConversationList = useCallback(async () => {
    const rows = await apiRequest<AssistantConversationSummaryResponse[]>(
      "/api/v1/ai/assistant/conversations?limit=20"
    );
    setConversations(rows);
    return rows;
  }, [apiRequest]);

  const fetchConversation = useCallback(
    async (conversationId: string) => {
      setLoadingHistory(true);
      try {
        const detail = await apiRequest<AssistantConversationDetailResponse>(
          `/api/v1/ai/assistant/conversations/${conversationId}`
        );
        pendingMessageRef.current = null;
        setActiveConversation(detail);
      } catch {
        Alert.alert("无法读取对话", "请检查网络后重试。");
      } finally {
        setLoadingHistory(false);
      }
    },
    [apiRequest]
  );

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    setLoadingHistory(true);
    fetchConversationList()
      .then(async (rows) => {
        if (cancelled || rows.length === 0) return;
        const detail = await apiRequest<AssistantConversationDetailResponse>(
          `/api/v1/ai/assistant/conversations/${rows[0].id}`
        );
        if (!cancelled) setActiveConversation(detail);
      })
      .catch(() => {
        if (!cancelled) Alert.alert("无法读取对话历史", "你仍可以稍后重试。");
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiRequest, fetchConversationList, status]);

  const startNewConversation = () => {
    pendingMessageRef.current = null;
    setActiveConversation(null);
    setQuestion("");
  };

  const removeConversation = () => {
    if (!activeConversation) return;
    Alert.alert("删除这段对话？", "消息和回答依据会一起删除，且无法恢复。", [
      { text: "取消", style: "cancel" },
      {
        text: "删除",
        style: "destructive",
        onPress: () => {
          setLoadingHistory(true);
          apiRequest<void>(`/api/v1/ai/assistant/conversations/${activeConversation.id}`, {
            method: "DELETE",
          })
            .then(async () => {
              const rows = await fetchConversationList();
              if (rows.length === 0) {
                pendingMessageRef.current = null;
                setActiveConversation(null);
              } else {
                await fetchConversation(rows[0].id);
              }
            })
            .catch(() => Alert.alert("删除失败", "请检查网络后重试。"))
            .finally(() => setLoadingHistory(false));
        },
      },
    ]);
  };

  const submit = async () => {
    const input = question.trim();
    if (input.length < 2) {
      Alert.alert("请补充问题", "例如：我今天吃得怎么样？");
      return;
    }
    if (status === "offline") {
      Alert.alert("当前处于离线模式", "AI 助手需要从后端读取并保存对话。");
      return;
    }
    setSending(true);
    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await apiRequest<AssistantConversationDetailResponse>(
          "/api/v1/ai/assistant/conversations",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          }
        );
        setActiveConversation(conversation);
        await fetchConversationList();
      }
      const pending = getPendingAssistantMessage(
        pendingMessageRef.current,
        conversation.id,
        input,
        uuidv4
      );
      pendingMessageRef.current = pending;
      const result = await apiRequest<AssistantConversationTurnResponse>(
        `/api/v1/ai/assistant/conversations/${conversation.id}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            client_message_id: pending.clientMessageId,
            question: input,
            reference_date: getToday(),
            locale: "zh-CN",
          }),
        }
      );
      pendingMessageRef.current = null;
      setActiveConversation(result.conversation);
      setQuestion("");
      await fetchConversationList();
    } catch {
      Alert.alert("助手暂时不可用", "问题仍保留在输入框中，请检查网络或 AI 设置后重试。");
    } finally {
      setSending(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="sparkles" size={26} color="#6A1B9A" />
          </View>
          <View style={styles.heroText}>
            <Text style={styles.title}>可追溯饮食助手</Text>
            <Text style={styles.subtitle}>多轮消息由你的账号保存，营养结论每轮重新查询</Text>
          </View>
          {activeConversation && (
            <TouchableOpacity accessibilityLabel="删除当前对话" onPress={removeConversation}>
              <Ionicons name="trash-outline" size={21} color="#C62828" />
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.guardrailCard}>
          <Ionicons name="shield-checkmark-outline" size={20} color="#1565C0" />
          <Text style={styles.guardrailText}>
            最近 8 条消息用于理解“那最近呢”等追问；真实摄入和食品数据仍必须重新调用只读工具。
          </Text>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.historyStrip}>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="新建 AI 对话"
            style={[styles.historyChip, !activeConversation && styles.historyChipActive]}
            onPress={startNewConversation}
          >
            <Ionicons name="add" size={15} color={!activeConversation ? "#fff" : "#455A64"} />
            <Text style={!activeConversation ? styles.historyTextActive : styles.historyText}>
              新对话
            </Text>
          </TouchableOpacity>
          {conversations.map((conversation) => (
            <TouchableOpacity
              key={conversation.id}
              accessibilityRole="button"
              accessibilityLabel={`打开对话：${conversation.title}`}
              style={[
                styles.historyChip,
                activeConversation?.id === conversation.id && styles.historyChipActive,
              ]}
              onPress={() => fetchConversation(conversation.id)}
            >
              <Text
                numberOfLines={1}
                style={
                  activeConversation?.id === conversation.id
                    ? styles.historyTextActive
                    : styles.historyText
                }
              >
                {conversation.title} · {conversation.message_count}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {loadingHistory ? (
          <ActivityIndicator style={styles.historyLoading} color="#2E7D32" />
        ) : activeConversation?.messages.length ? (
          <View style={styles.messages}>
            {activeConversation.messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </View>
        ) : (
          <View style={styles.emptyConversation}>
            <Ionicons name="chatbubbles-outline" size={28} color="#90A4AE" />
            <Text style={styles.emptyTitle}>开始一段新对话</Text>
            <Text style={styles.emptyText}>可以连续追问，但每次营养事实都会重新读取当前数据。</Text>
          </View>
        )}

        <View style={styles.suggestions}>
          {SUGGESTIONS.map((suggestion) => (
            <TouchableOpacity
              key={suggestion}
              style={styles.suggestion}
              onPress={() => setQuestion(suggestion)}
            >
              <Text style={styles.suggestionText}>{suggestion}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TextInput
          accessibilityLabel="向 AI 饮食助手提问"
          style={styles.input}
          multiline
          maxLength={500}
          value={question}
          placeholder="例如：那最近七天的趋势呢？"
          placeholderTextColor="#90A4AE"
          onChangeText={setQuestion}
        />
        <TouchableOpacity
          accessibilityRole="button"
          disabled={sending}
          style={[styles.submitButton, sending && styles.disabled]}
          onPress={submit}
        >
          {sending ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="send" size={18} color="#fff" />
              <Text style={styles.submitText}>发送并查询数据</Text>
            </>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function MessageBubble({ message }: { message: AssistantConversationMessageResponse }) {
  const isUser = message.role === "user";
  return (
    <View style={[styles.messageBubble, isUser ? styles.userBubble : styles.assistantBubble]}>
      <Text style={isUser ? styles.userContent : styles.assistantContent}>{message.content}</Text>
      {!isUser && (
        <>
          {(message.warnings ?? []).map((warning) => (
            <Text key={warning} style={styles.warning}>
              • {warning}
            </Text>
          ))}
          {message.evidence.length > 0 && <Text style={styles.evidenceTitle}>查询依据</Text>}
          {message.evidence.map((item) => (
            <View key={item.call_id} style={styles.evidenceCard}>
              <Text style={styles.evidenceName}>{getToolLabel(item.tool_name)}</Text>
              <Text style={styles.evidenceSummary}>{item.summary}</Text>
            </View>
          ))}
          <Text style={styles.meta}>
            {getAssistantMessageProviderLabel(message)} · {message.model ?? "unknown"} ·
            {message.latency_ms ?? 0} ms ·
            {(message.input_tokens ?? 0) + (message.output_tokens ?? 0)} tokens · Prompt{" "}
            {message.prompt_version ?? "unknown"}
          </Text>
          {message.trace_id && (
            <Text style={styles.trace}>Trace {message.trace_id.slice(0, 8)}</Text>
          )}
          {message.disclaimer && <Text style={styles.disclaimer}>{message.disclaimer}</Text>}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F5F7F6" },
  content: { padding: 16, paddingBottom: 48 },
  hero: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 14 },
  heroIcon: {
    width: 50,
    height: 50,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F3E5F5",
  },
  heroText: { flex: 1 },
  title: { fontSize: 21, fontWeight: "800", color: "#263238" },
  subtitle: { marginTop: 3, color: "#607D8B", fontSize: 12, lineHeight: 17 },
  guardrailCard: {
    flexDirection: "row",
    gap: 9,
    padding: 13,
    borderRadius: 12,
    backgroundColor: "#E3F2FD",
  },
  guardrailText: { flex: 1, color: "#37474F", fontSize: 12, lineHeight: 18 },
  historyStrip: { marginVertical: 14 },
  historyChip: {
    maxWidth: 190,
    height: 34,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 11,
    marginRight: 8,
    borderRadius: 17,
    backgroundColor: "#ECEFF1",
  },
  historyChipActive: { backgroundColor: "#2E7D32" },
  historyText: { color: "#455A64", fontSize: 12 },
  historyTextActive: { color: "#fff", fontSize: 12, fontWeight: "700" },
  historyLoading: { marginVertical: 28 },
  messages: { gap: 10, marginBottom: 14 },
  messageBubble: { maxWidth: "92%", borderRadius: 14, padding: 13 },
  userBubble: { alignSelf: "flex-end", backgroundColor: "#2E7D32" },
  assistantBubble: { alignSelf: "flex-start", backgroundColor: "#fff" },
  userContent: { color: "#fff", fontSize: 14, lineHeight: 21 },
  assistantContent: { color: "#37474F", fontSize: 14, lineHeight: 21 },
  emptyConversation: { alignItems: "center", paddingVertical: 26 },
  emptyTitle: { color: "#455A64", fontWeight: "700", marginTop: 7 },
  emptyText: { color: "#78909C", fontSize: 12, marginTop: 5, textAlign: "center" },
  suggestions: { gap: 7, marginBottom: 12 },
  suggestion: {
    alignSelf: "flex-start",
    backgroundColor: "#ECEFF1",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  suggestionText: { color: "#546E7A", fontSize: 12 },
  input: {
    minHeight: 82,
    padding: 13,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#DDE4E1",
    backgroundColor: "#fff",
    color: "#263238",
    fontSize: 15,
    lineHeight: 21,
    textAlignVertical: "top",
  },
  submitButton: {
    height: 48,
    marginTop: 12,
    borderRadius: 12,
    backgroundColor: "#2E7D32",
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  submitText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  disabled: { opacity: 0.5 },
  warning: { color: "#E65100", fontSize: 12, lineHeight: 18, marginTop: 8 },
  evidenceTitle: { marginTop: 12, color: "#455A64", fontSize: 12, fontWeight: "700" },
  evidenceCard: { backgroundColor: "#E8F4FD", borderRadius: 9, padding: 9, marginTop: 6 },
  evidenceName: { color: "#1565C0", fontSize: 11, fontWeight: "700" },
  evidenceSummary: { color: "#455A64", fontSize: 11, lineHeight: 17, marginTop: 4 },
  meta: { marginTop: 9, color: "#90A4AE", fontSize: 10, lineHeight: 15 },
  trace: { marginTop: 2, color: "#90A4AE", fontSize: 9 },
  disclaimer: { marginTop: 5, color: "#78909C", fontSize: 10, lineHeight: 15 },
});
