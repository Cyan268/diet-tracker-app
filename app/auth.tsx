import { ApiError, NetworkError } from "@/api/http";
import { useAuth } from "@/features/auth/AuthContext";
import { fetchPublicRuntimeConfig } from "@/features/auth/publicRuntimeConfig";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

function errorMessage(error: unknown): string {
  if (error instanceof NetworkError) return "无法连接服务器，请检查网络和 API 地址。";
  if (error instanceof ApiError) {
    if (error.status === 409) return "该邮箱已注册，请直接登录。";
    if (error.status === 401) return "邮箱或密码错误。";
    if (error.status === 403) return "当前演示环境已关闭公开注册。";
    if (error.status === 429) return "尝试次数过多，请稍后再试。";
    if (error.status === 503) return "认证保护暂时不可用，请稍后再试。";
    if (error.status === 422) return "请检查邮箱格式和密码长度。";
  }
  return "操作失败，请稍后重试。";
}

export default function AuthScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [configResolved, setConfigResolved] = useState(false);
  const modes: ("login" | "register")[] = registrationEnabled ? ["login", "register"] : ["login"];

  useEffect(() => {
    let active = true;
    fetchPublicRuntimeConfig()
      .then((config) => {
        if (!active) return;
        setRegistrationEnabled(config.registration_enabled);
        setConfigResolved(true);
        if (!config.registration_enabled) setMode("login");
      })
      .catch(() => {
        if (!active) return;
        setRegistrationEnabled(false);
        setConfigResolved(false);
        setMode("login");
      });
    return () => {
      active = false;
    };
  }, []);

  const submit = async () => {
    const normalizedEmail = email.trim();
    if (!normalizedEmail || !password) {
      setError("请输入邮箱和密码。");
      return;
    }
    if (mode === "register" && password.length < 10) {
      setError("注册密码至少需要 10 个字符。");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await (mode === "login" ? login : register)(normalizedEmail, password);
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.card}>
        <Text style={styles.brand}>NutriPilot</Text>
        <Text style={styles.subtitle}>AI 饮食记录与营养分析</Text>

        <View style={styles.tabs}>
          {modes.map((item) => (
            <TouchableOpacity
              key={item}
              style={[styles.tab, mode === item && styles.activeTab]}
              onPress={() => {
                setMode(item);
                setError(null);
              }}
            >
              <Text style={[styles.tabText, mode === item && styles.activeTabText]}>
                {item === "login" ? "登录" : "注册"}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        {!registrationEnabled && (
          <Text style={styles.registrationHint}>
            {configResolved
              ? "当前演示环境关闭公开注册，请使用演示账号登录。"
              : "注册入口暂不可用；登录功能仍可正常使用。"}
          </Text>
        )}

        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          placeholder="邮箱"
          keyboardType="email-address"
          autoCapitalize="none"
          autoComplete="email"
          editable={!submitting}
        />
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          placeholder={mode === "register" ? "密码（至少 10 个字符）" : "密码"}
          secureTextEntry
          autoCapitalize="none"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          editable={!submitting}
          onSubmitEditing={submit}
        />

        {error && <Text style={styles.error}>{error}</Text>}

        <TouchableOpacity
          style={[styles.submit, submitting && styles.disabled]}
          onPress={submit}
          disabled={submitting}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitText}>{mode === "login" ? "登录" : "创建账号"}</Text>
          )}
        </TouchableOpacity>
        <Text style={styles.offlineHint}>首次登录需要网络；登录后可继续使用本地离线记录。</Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    backgroundColor: "#f3f7f3",
    paddingHorizontal: 24,
  },
  card: { backgroundColor: "#fff", borderRadius: 20, padding: 24, elevation: 3 },
  brand: { fontSize: 30, fontWeight: "800", color: "#2E7D32", textAlign: "center" },
  subtitle: { fontSize: 14, color: "#777", textAlign: "center", marginTop: 6 },
  tabs: { flexDirection: "row", marginTop: 28, marginBottom: 20, gap: 8 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: "center" },
  activeTab: { backgroundColor: "#E8F5E9" },
  tabText: { color: "#888", fontWeight: "600" },
  activeTabText: { color: "#2E7D32" },
  registrationHint: {
    color: "#7A6845",
    backgroundColor: "#FFF8E1",
    borderRadius: 10,
    padding: 10,
    fontSize: 12,
    marginBottom: 12,
  },
  input: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    fontSize: 15,
    marginBottom: 12,
  },
  error: { color: "#D32F2F", fontSize: 13, marginBottom: 12 },
  submit: {
    backgroundColor: "#4CAF50",
    borderRadius: 12,
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  disabled: { opacity: 0.65 },
  submitText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  offlineHint: { color: "#999", fontSize: 12, textAlign: "center", marginTop: 16 },
});
