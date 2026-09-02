import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";

const mealOptions = [
  { key: "breakfast", label: "早餐", icon: "sunny" as const, color: "#FF9800" },
  { key: "lunch", label: "午餐", icon: "restaurant" as const, color: "#4CAF50" },
  { key: "dinner", label: "晚餐", icon: "moon" as const, color: "#5C6BC0" },
  { key: "snack", label: "加餐", icon: "nutrition" as const, color: "#FF5722" },
  { key: "drink", label: "饮品", icon: "cafe" as const, color: "#795548" },
];

export default function AddScreen() {
  const handlePress = (key: string) => {
    if (key === "drink") {
      router.push("/add-drink");
    } else {
      router.push({ pathname: "/add-food", params: { mealType: key } });
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>选择记录类型</Text>
      <Text style={styles.subtitle}>记录今天的每一餐</Text>

      <TouchableOpacity style={styles.aiCard} onPress={() => router.push("/ai-add")}>
        <View style={styles.aiIcon}>
          <Ionicons name="sparkles" size={28} color="#6A1B9A" />
        </View>
        <View style={styles.aiContent}>
          <View style={styles.aiTitleRow}>
            <Text style={styles.aiTitle}>AI 自然语言记录</Text>
            <Text style={styles.aiBadge}>Phase 2</Text>
          </View>
          <Text style={styles.aiDescription}>
            说一句“午餐吃了200克鸡胸肉和一碗米饭”生成待确认草稿
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color="#9E9E9E" />
      </TouchableOpacity>

      <View style={styles.grid}>
        {mealOptions.map((option) => (
          <TouchableOpacity
            key={option.key}
            style={styles.optionCard}
            onPress={() => handlePress(option.key)}
          >
            <View style={[styles.iconCircle, { backgroundColor: option.color + "20" }]}>
              <Ionicons name={option.icon} size={32} color={option.color} />
            </View>
            <Text style={styles.optionLabel}>{option.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.tipCard}>
        <Ionicons name="information-circle" size={20} color="#2196F3" />
        <Text style={styles.tipText}>
          选择餐次后，可以搜索食物或手动输入，系统会自动估算热量和营养素。
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20 },
  title: { fontSize: 24, fontWeight: "bold", color: "#333" },
  subtitle: { fontSize: 14, color: "#666", marginTop: 4, marginBottom: 24 },
  aiCard: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 16,
    marginBottom: 18,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: "#E1BEE7",
  },
  aiIcon: {
    width: 50,
    height: 50,
    borderRadius: 14,
    backgroundColor: "#F3E5F5",
    justifyContent: "center",
    alignItems: "center",
  },
  aiContent: { flex: 1 },
  aiTitleRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  aiTitle: { fontSize: 16, fontWeight: "700", color: "#263238" },
  aiBadge: {
    fontSize: 10,
    color: "#6A1B9A",
    backgroundColor: "#F3E5F5",
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 5,
  },
  aiDescription: { color: "#607D8B", fontSize: 12, lineHeight: 17, marginTop: 5 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  optionCard: {
    width: "47%",
    backgroundColor: "#fff",
    padding: 20,
    borderRadius: 16,
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  iconCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 8,
  },
  optionLabel: { fontSize: 16, fontWeight: "600", color: "#333" },
  tipCard: {
    flexDirection: "row",
    backgroundColor: "#E3F2FD",
    padding: 14,
    borderRadius: 10,
    marginTop: 24,
    alignItems: "flex-start",
    gap: 8,
  },
  tipText: { flex: 1, fontSize: 13, color: "#555", lineHeight: 18 },
});
