import { View, Text, StyleSheet, TouchableOpacity, Alert } from "react-native";
import { Swipeable } from "react-native-gesture-handler";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useRef } from "react";
import { deleteLog } from "@/db/repositories/logRepository";
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
  onDeleted?: () => void;
}

export function FoodLogItem({ log, onDeleted }: FoodLogItemProps) {
  const swipeableRef = useRef<Swipeable>(null);
  const label = MEAL_LABELS[log.mealType] ?? log.mealType;
  const color = MEAL_COLORS[log.mealType] ?? "#999";

  const handlePress = () => {
    router.push({ pathname: "/edit-log", params: { logId: log.id } });
  };

  const handleDelete = () => {
    Alert.alert("删除记录", `确定要删除「${log.customName ?? "未知食物"}」吗？`, [
      { text: "取消", style: "cancel" },
      {
        text: "删除",
        style: "destructive",
        onPress: async () => {
          await deleteLog(log.id);
          onDeleted?.();
        },
      },
    ]);
  };

  const renderRightActions = () => (
    <TouchableOpacity style={styles.deleteAction} onPress={handleDelete}>
      <Ionicons name="trash-outline" size={20} color="#fff" />
      <Text style={styles.deleteText}>删除</Text>
    </TouchableOpacity>
  );

  return (
    <Swipeable ref={swipeableRef} renderRightActions={renderRightActions} overshootRight={false}>
      <TouchableOpacity style={styles.container} onPress={handlePress} activeOpacity={0.7}>
        <View style={[styles.badge, { backgroundColor: color + "20" }]}>
          <Text style={[styles.badgeText, { color }]}>{label}</Text>
        </View>
        <View style={styles.content}>
          <Text style={styles.name}>{log.customName ?? "未知食物"}</Text>
          <Text style={styles.detail}>
            {log.amount}
            {log.unit} · {Math.round(log.kcal)} kcal
          </Text>
        </View>
        <Text style={styles.macro}>
          P{Math.round(log.protein)}g F{Math.round(log.fat)}g C{Math.round(log.carbs)}g
        </Text>
      </TouchableOpacity>
    </Swipeable>
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
  deleteAction: {
    backgroundColor: "#F44336",
    justifyContent: "center",
    alignItems: "center",
    width: 72,
    borderRadius: 10,
    marginBottom: 8,
    marginLeft: 8,
    flexDirection: "column",
    gap: 2,
  },
  deleteText: {
    color: "#fff",
    fontSize: 11,
    fontWeight: "600",
  },
});
