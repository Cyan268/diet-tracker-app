import {
  acceptRemoteVersion,
  keepLocalVersion,
  listSyncConflicts,
  type SyncConflict,
} from "@/db/repositories/syncConflictRepository";
import { useAuth } from "@/features/auth/AuthContext";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

export default function SyncConflictsScreen() {
  const { syncNow } = useAuth();
  const [conflicts, setConflicts] = useState<SyncConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setConflicts(await listSyncConflicts());
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => Alert.alert("读取失败", "暂时无法读取同步冲突。"));
    }, [load])
  );

  const resolve = async (conflict: SyncConflict, choice: "local" | "remote") => {
    setResolvingId(conflict.id);
    try {
      if (choice === "local") await keepLocalVersion(conflict.id);
      else await acceptRemoteVersion(conflict.id);
      await syncNow();
      await load();
    } catch {
      Alert.alert("处理失败", "记录可能已发生新变化，请刷新后重试。所有本地数据仍会保留。 ");
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>同步冲突</Text>
        <View style={styles.backButton} />
      </View>

      {loading ? (
        <ActivityIndicator style={styles.loading} size="large" color="#4CAF50" />
      ) : conflicts.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="checkmark-circle-outline" size={52} color="#4CAF50" />
          <Text style={styles.emptyTitle}>没有待处理冲突</Text>
          <Text style={styles.emptyText}>本地记录与云端版本保持一致。</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          <Text style={styles.hint}>
            两台设备修改了同一条记录。请选择保留本机内容，或使用最新云端版本。
          </Text>
          {conflicts.map((conflict) => {
            const remoteLog = conflict.remote.log;
            const busy = resolvingId === conflict.id;
            return (
              <View key={conflict.id} style={styles.card}>
                <Text style={styles.cardTitle}>
                  {conflict.local?.customName ?? remoteLog?.custom_name ?? "已删除的饮食记录"}
                </Text>
                <View style={styles.compareRow}>
                  <View style={styles.versionBox}>
                    <Text style={styles.versionLabel}>本机</Text>
                    <Text style={styles.versionValue}>
                      {conflict.local
                        ? `${conflict.local.amount}${conflict.local.unit} · ${Math.round(conflict.local.kcal)} kcal`
                        : "已删除"}
                    </Text>
                  </View>
                  <View style={styles.versionBox}>
                    <Text style={styles.versionLabel}>云端</Text>
                    <Text style={styles.versionValue}>
                      {conflict.remoteOperation === "delete" || !remoteLog
                        ? "已删除"
                        : `${remoteLog.amount}${remoteLog.unit} · ${Math.round(remoteLog.kcal)} kcal`}
                    </Text>
                  </View>
                </View>
                <View style={styles.actions}>
                  <TouchableOpacity
                    disabled={busy}
                    style={[styles.button, styles.localButton]}
                    onPress={() => resolve(conflict, "local")}
                  >
                    <Text style={styles.localButtonText}>{busy ? "处理中" : "保留本机"}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    disabled={busy}
                    style={[styles.button, styles.remoteButton]}
                    onPress={() => resolve(conflict, "remote")}
                  >
                    <Text style={styles.remoteButtonText}>{busy ? "处理中" : "使用云端"}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f5f5f5" },
  header: {
    height: 56,
    backgroundColor: "#fff",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 0.5,
    borderBottomColor: "#ddd",
  },
  backButton: { width: 52, alignItems: "center" },
  title: { fontSize: 18, fontWeight: "600", color: "#222" },
  loading: { flex: 1 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32 },
  emptyTitle: { marginTop: 14, fontSize: 18, fontWeight: "600", color: "#333" },
  emptyText: { marginTop: 6, fontSize: 13, color: "#888" },
  list: { padding: 16, paddingBottom: 40 },
  hint: { fontSize: 13, color: "#666", lineHeight: 20, marginBottom: 12 },
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 16, marginBottom: 12 },
  cardTitle: { fontSize: 16, fontWeight: "600", color: "#333", marginBottom: 12 },
  compareRow: { flexDirection: "row", gap: 10 },
  versionBox: { flex: 1, backgroundColor: "#f7f7f7", borderRadius: 8, padding: 10 },
  versionLabel: { fontSize: 12, color: "#888", marginBottom: 5 },
  versionValue: { fontSize: 13, color: "#333", lineHeight: 18 },
  actions: { flexDirection: "row", gap: 10, marginTop: 14 },
  button: { flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 8 },
  localButton: { borderWidth: 1, borderColor: "#4CAF50" },
  remoteButton: { backgroundColor: "#4CAF50" },
  localButtonText: { color: "#388E3C", fontWeight: "600" },
  remoteButtonText: { color: "#fff", fontWeight: "600" },
});
