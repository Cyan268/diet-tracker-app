import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { AiCredentialStatusResponse } from "@/api/types";
import { useAuth } from "@/features/auth/AuthContext";
import { canManageAiCredentials, isDemoAccount } from "@/features/demo/demoAccount";

export default function AiSettingsScreen() {
  const { apiRequest, status: authStatus, user } = useAuth();
  const [credential, setCredential] = useState<AiCredentialStatusResponse | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const demoAccount = isDemoAccount(user);
  const canManage = canManageAiCredentials(user, authStatus);

  useEffect(() => {
    if (demoAccount) {
      setCredential({
        configured: false,
        provider: "openai",
        key_hint: null,
        updated_at: null,
      });
      setLoading(false);
      return;
    }
    if (authStatus === "offline") {
      setLoading(false);
      return;
    }
    apiRequest<AiCredentialStatusResponse>("/api/v1/ai/credentials")
      .then(setCredential)
      .catch(() => Alert.alert("读取失败", "暂时无法读取 AI 服务设置，请稍后重试。"))
      .finally(() => setLoading(false));
  }, [apiRequest, authStatus, demoAccount]);

  const save = async () => {
    if (demoAccount) {
      Alert.alert("演示账号安全限制", "共享演示账号不会保存 API Key，也不会调用服务端付费模型。");
      return;
    }
    const value = apiKey.trim();
    if (value.length < 20) {
      Alert.alert("Key 格式不完整", "请粘贴完整的 OpenAI API Key。");
      return;
    }
    setSaving(true);
    try {
      const result = await apiRequest<AiCredentialStatusResponse>("/api/v1/ai/credentials", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: value }),
      });
      setCredential(result);
      setApiKey("");
      setShowKey(false);
      Alert.alert(
        "保存成功",
        "之后的 AI 识别会优先使用你的 OpenAI API Key。首次分析会验证 Key 是否可用。"
      );
    } catch {
      Alert.alert("保存失败", "Key 没有保存，请检查网络后重试。");
    } finally {
      setSaving(false);
    }
  };

  const clear = () => {
    Alert.alert("删除 API Key", "删除后将恢复使用项目默认的规则识别或服务端 Provider。", [
      { text: "取消", style: "cancel" },
      {
        text: "删除",
        style: "destructive",
        onPress: async () => {
          setSaving(true);
          try {
            await apiRequest<void>("/api/v1/ai/credentials", { method: "DELETE" });
            setCredential({
              configured: false,
              provider: "openai",
              key_hint: null,
              updated_at: null,
            });
            setApiKey("");
          } catch {
            Alert.alert("删除失败", "请检查网络后重试。");
          } finally {
            setSaving(false);
          }
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.header}>
        <TouchableOpacity
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={24} color="#263238" />
        </TouchableOpacity>
        <Text style={styles.title}>AI 服务设置</Text>
        <View style={styles.headerSpacer} />
      </View>

      <View style={styles.securityCard}>
        <Ionicons name="shield-checkmark" size={24} color="#1565C0" />
        <View style={styles.securityCopy}>
          <Text style={styles.securityTitle}>服务端加密保存</Text>
          <Text style={styles.securityText}>
            Key 不会写入 App 本地数据库，也不会再次完整返回。后端使用 AES-GCM
            加密，只展示末四位。正式部署必须使用 HTTPS。
          </Text>
        </View>
      </View>

      {demoAccount && (
        <View style={styles.demoCard}>
          <Ionicons name="flask-outline" size={22} color="#8D6E00" />
          <Text style={styles.demoText}>
            当前是可重置演示账号。为避免共享账号泄露凭证、滥用资源或产生费用，后端强制使用本地规则
            Provider，不能保存个人 API Key，并限制 AI 请求频率。
          </Text>
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.label}>当前状态</Text>
        {loading ? (
          <ActivityIndicator color="#4CAF50" style={styles.loader} />
        ) : credential?.configured ? (
          <View style={styles.statusRow}>
            <View style={styles.statusIcon}>
              <Ionicons name="checkmark" size={16} color="#fff" />
            </View>
            <View>
              <Text style={styles.configured}>已配置 OpenAI</Text>
              <Text style={styles.hint}>Key {credential.key_hint}</Text>
            </View>
          </View>
        ) : (
          <Text style={styles.emptyStatus}>尚未配置，将使用规则识别。</Text>
        )}

        <Text style={styles.inputLabel}>
          {credential?.configured ? "替换 API Key" : "OpenAI API Key"}
        </Text>
        <View style={styles.inputRow}>
          <TextInput
            accessibilityLabel="OpenAI API Key"
            style={styles.input}
            value={apiKey}
            onChangeText={setApiKey}
            placeholder="粘贴你的 API Key"
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry={!showKey}
            editable={!saving && canManage}
          />
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel={showKey ? "隐藏 API Key" : "显示 API Key"}
            style={styles.eyeButton}
            onPress={() => setShowKey((value) => !value)}
          >
            <Ionicons
              name={showKey ? "eye-off-outline" : "eye-outline"}
              size={21}
              color="#607D8B"
            />
          </TouchableOpacity>
        </View>
        <Text style={styles.helpText}>
          保存操作不会主动产生模型费用；第一次生成 AI 草稿时才会调用模型。请在 OpenAI
          控制台设置用量预算并定期轮换 Key。
        </Text>

        {authStatus === "offline" && !demoAccount && (
          <Text style={styles.offline}>当前离线，联网后才能修改 Key。</Text>
        )}

        <TouchableOpacity
          accessibilityRole="button"
          style={[styles.saveButton, (saving || !canManage) && styles.disabled]}
          disabled={saving || !canManage}
          onPress={save}
        >
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveText}>加密保存</Text>
          )}
        </TouchableOpacity>

        {credential?.configured && (
          <TouchableOpacity
            accessibilityRole="button"
            style={[styles.deleteButton, saving && styles.disabled]}
            disabled={saving}
            onPress={clear}
          >
            <Text style={styles.deleteText}>删除已保存的 Key</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.boundaryCard}>
        <Text style={styles.boundaryTitle}>安全边界</Text>
        <Text style={styles.boundaryText}>
          后端需要在调用模型时临时解密
          Key，因此这是“加密存储”而不是端到端加密。服务器管理员仍需保护主密钥、限制日志和数据库权限。
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F4F7F5" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 48,
    paddingBottom: 14,
    backgroundColor: "#fff",
  },
  backButton: { padding: 6 },
  title: { fontSize: 18, fontWeight: "700", color: "#263238" },
  headerSpacer: { width: 36 },
  securityCard: {
    flexDirection: "row",
    gap: 12,
    margin: 16,
    padding: 15,
    borderRadius: 12,
    backgroundColor: "#E3F2FD",
  },
  securityCopy: { flex: 1 },
  securityTitle: { fontSize: 14, fontWeight: "700", color: "#0D47A1" },
  securityText: { fontSize: 12, lineHeight: 18, color: "#315A73", marginTop: 4 },
  demoCard: {
    flexDirection: "row",
    gap: 10,
    marginHorizontal: 16,
    marginBottom: 16,
    padding: 14,
    borderRadius: 12,
    backgroundColor: "#FFF8E1",
  },
  demoText: { flex: 1, color: "#795548", fontSize: 12, lineHeight: 18 },
  card: { marginHorizontal: 16, padding: 16, borderRadius: 14, backgroundColor: "#fff" },
  label: { fontSize: 13, fontWeight: "600", color: "#546E7A" },
  loader: { alignSelf: "flex-start", marginVertical: 14 },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 10 },
  statusIcon: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#2E7D32",
    alignItems: "center",
    justifyContent: "center",
  },
  configured: { fontSize: 14, fontWeight: "700", color: "#2E7D32" },
  hint: { fontSize: 12, color: "#78909C", marginTop: 2 },
  emptyStatus: { color: "#78909C", marginTop: 10, fontSize: 13 },
  inputLabel: { fontSize: 13, fontWeight: "600", color: "#37474F", marginTop: 22, marginBottom: 8 },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#CFD8DC",
    borderRadius: 10,
    backgroundColor: "#FAFAFA",
  },
  input: { flex: 1, height: 48, paddingHorizontal: 12, color: "#263238" },
  eyeButton: { padding: 12 },
  helpText: { color: "#78909C", fontSize: 11, lineHeight: 17, marginTop: 9 },
  offline: { color: "#E65100", fontSize: 12, marginTop: 10 },
  saveButton: {
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    backgroundColor: "#2E7D32",
    marginTop: 18,
  },
  saveText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  deleteButton: {
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#EF9A9A",
    marginTop: 10,
  },
  deleteText: { color: "#C62828", fontWeight: "600" },
  disabled: { opacity: 0.45 },
  boundaryCard: {
    marginHorizontal: 16,
    marginTop: 14,
    marginBottom: 36,
    padding: 14,
    borderRadius: 12,
    backgroundColor: "#FFF8E1",
  },
  boundaryTitle: { color: "#8D6E00", fontWeight: "700", fontSize: 13 },
  boundaryText: { color: "#795548", fontSize: 11, lineHeight: 17, marginTop: 5 },
});
