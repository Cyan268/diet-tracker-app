import { View, Text, StyleSheet } from "react-native";
import type { FoodLog } from "@/types/log";

const MEAL_LABELS: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
  drink: "饮品",
};

const MEAL_COLORS: Record<string, string> = {
  breakfast: "#FF9800",
  lunch: "#4CAF50",
  dinner: "#5C6BC0",
  snack: "#FF5722",
  drink: "#795548",
};

interface FoodLogItemProps {
  log: FoodLog;
}

export function FoodLogItem({ log }: FoodLogItemProps) {
  const label = MEAL_LABELS[log.mealType] ?? log.mealType;
  const color = MEAL_COLORS[log.mealType] ?? "#999";

  return (
    <View style={styles.container}>
      <View style={[styles.badge, { backgroundColor: color + "20" }]}>
        <Text style={[styles.badgeText, { color }]}>{label}</Text>
      </View>
      <View style={styles.content}>
        <Text style={styles.name}>{log.customName ?? "未知食物"}</Text>
        <Text style={styles.detail}>
          {log.amount}{log.unit} · {Math.round(log.kcal)} kcal
        </Text>
      </View>
      <Text style={styles.macro}>
        P{Math.round(log.protein)}g F{Math.round(log.fat)}g C{Math.round(log.carbs)}g
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    padding: 12,
    borderRadius: 10,
    marginBottom: 8,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginRight: 10,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "600",
  },
  content: {
    flex: 1,
  },
  name: {
    fontSize: 14,
    fontWeight: "500",
    color: "#333",
  },
  detail: {
    fontSize: 12,
    color: "#999",
    marginTop: 2,
  },
  macro: {
    fontSize: 11,
    color: "#999",
  },
});
