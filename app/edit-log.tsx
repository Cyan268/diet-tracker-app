import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
} from "react-native";
import { useLocalSearchParams, router } from "expo-router";
import { useState, useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { getLogById, updateLog } from "../src/db/repositories/logRepository";
import { getFoodById } from "../src/db/repositories/foodRepository";
import { calcByGram } from "../src/features/food/foodCalculator";
import { round } from "../src/utils/number";
import type { FoodLog } from "../src/types/log";
import type { FoodItem } from "../src/types/nutrition";

const MEAL_LABELS: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
  drink: "饮品",
};

export default function EditLogScreen() {
  const { logId } = useLocalSearchParams<{ logId: string }>();
  const [log, setLog] = useState<FoodLog | null>(null);
  const [foodItem, setFoodItem] = useState<FoodItem | null>(null);
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("g");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      if (!logId) return;
      const l = await getLogById(logId);
      if (!l) {
        Alert.alert("错误", "找不到该记录");
        router.back();
        return;
      }
      setLog(l);
      setAmount(String(l.amount));
      setUnit(l.unit);
      setNote(l.note ?? "");

      if (l.foodItemId) {
        const food = await getFoodById(l.foodItemId);
        if (food) setFoodItem(food);
      }
      setLoading(false);
    })();
  }, [logId]);

  const isDrink = log?.mealType === "drink";

  const getGrams = (): number => {
    if (!foodItem) return 0;
    if (unit === "g") return parseFloat(amount) || 0;
    if (foodItem.servingWeightG) {
      return (parseFloat(amount) || 0) * foodItem.servingWeightG;
    }
    return parseFloat(amount) || 0;
  };

  const grams = getGrams();
  const nutrition = foodItem && grams > 0 ? calcByGram(foodItem, grams) : null;

  const handleSave = async () => {
    if (!log) return;

    if (!isDrink) {
      const amountNum = parseFloat(amount);
      if (!amountNum || amountNum <= 0) {
        Alert.alert("提示", "请输入有效数量");
        return;
      }
    }

    setSaving(true);
    try {
      const updates: Parameters<typeof updateLog>[1] = { note: note.trim() ? note : null };

      if (!isDrink && nutrition) {
        updates.amount = parseFloat(amount) || 0;
        updates.unit = unit;
        updates.kcal = nutrition.kcal;
        updates.protein = nutrition.protein;
        updates.fat = nutrition.fat;
        updates.carbs = nutrition.carbs;
        updates.sugar = nutrition.sugar;
        updates.sodium = nutrition.sodium;
        updates.caffeine = nutrition.caffeine;
      }

      await updateLog(log.id, updates);
      router.back();
    } catch {
      Alert.alert("错误", "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>编辑{MEAL_LABELS[log?.mealType ?? ""] ?? ""}记录</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>食物</Text>
        <Text style={styles.foodName}>{log?.customName ?? "未知食物"}</Text>
      </View>

      {isDrink ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>饮品记录</Text>
          <Text style={styles.drinkInfo}>
            {log?.amount}
            {log?.unit} · {Math.round(log?.kcal ?? 0)} kcal · 糖 {round(log?.sugar ?? 0, 1)}g ·
            咖啡因 {Math.round(log?.caffeine ?? 0)}mg
          </Text>
          <Text style={styles.drinkHint}>饮品记录暂不支持修改配方，仅可编辑备注。</Text>
        </View>
      ) : (
        <>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>数量</Text>
            <View style={styles.amountRow}>
              <TextInput
                style={styles.amountInput}
                placeholder="数量"
                keyboardType="numeric"
                value={amount}
                onChangeText={setAmount}
              />
              {foodItem?.servingUnit && foodItem?.servingWeightG ? (
                <TouchableOpacity
                  style={styles.unitBtn}
                  onPress={() => setUnit(unit === "g" ? foodItem.servingUnit! : "g")}
                >
                  <Text style={styles.unitText}>{unit}</Text>
                  <Ionicons name="swap-horizontal" size={16} color="#4CAF50" />
                </TouchableOpacity>
              ) : (
                <View style={styles.unitDisplay}>
                  <Text style={styles.unitText}>{unit}</Text>
                </View>
              )}
            </View>
            {unit !== "g" && foodItem?.servingWeightG && (
              <Text style={styles.gramHint}>≈ {round(grams)}g</Text>
            )}
          </View>

          {nutrition && grams > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>营养素预览</Text>
              <View style={styles.previewGrid}>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.kcal)}</Text>
                  <Text style={styles.previewLabel}>kcal</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.protein, 1)}</Text>
                  <Text style={styles.previewLabel}>蛋白质(g)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.fat, 1)}</Text>
                  <Text style={styles.previewLabel}>脂肪(g)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.carbs, 1)}</Text>
                  <Text style={styles.previewLabel}>碳水(g)</Text>
                </View>
              </View>
            </View>
          )}
        </>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>备注</Text>
        <TextInput
          style={styles.noteInput}
          placeholder="添加备注（可选）"
          value={note}
          onChangeText={setNote}
          multiline
        />
      </View>

      <TouchableOpacity
        style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
        onPress={handleSave}
        disabled={saving}
      >
        <Text style={styles.saveBtnText}>{saving ? "保存中..." : "保存修改"}</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#f5f5f5",
  },
  loadingText: { fontSize: 14, color: "#999" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 50,
    paddingBottom: 12,
    backgroundColor: "#fff",
  },
  backBtn: { padding: 4 },
  title: { fontSize: 18, fontWeight: "600", color: "#333" },
  section: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 12,
    padding: 14,
    borderRadius: 12,
  },
  sectionTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 10 },
  foodName: { fontSize: 16, fontWeight: "500", color: "#333" },
  drinkInfo: { fontSize: 14, color: "#333", lineHeight: 20 },
  drinkHint: { fontSize: 12, color: "#999", marginTop: 8 },
  amountRow: { flexDirection: "row", gap: 8 },
  amountInput: {
    flex: 1,
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 16,
    color: "#333",
  },
  unitBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    gap: 4,
  },
  unitDisplay: {
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    justifyContent: "center",
  },
  unitText: { fontSize: 15, color: "#4CAF50", fontWeight: "600" },
  gramHint: { fontSize: 12, color: "#999", marginTop: 6, marginLeft: 4 },
  previewGrid: { flexDirection: "row", justifyContent: "space-around" },
  previewItem: { alignItems: "center" },
  previewValue: { fontSize: 16, fontWeight: "bold", color: "#4CAF50" },
  previewLabel: { fontSize: 11, color: "#999", marginTop: 2 },
  noteInput: {
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 12,
    fontSize: 14,
    color: "#333",
    minHeight: 44,
    textAlignVertical: "top",
  },
  saveBtn: {
    backgroundColor: "#4CAF50",
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 40,
    borderRadius: 12,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
