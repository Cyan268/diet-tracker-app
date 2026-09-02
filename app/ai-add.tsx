import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useMemo, useState } from "react";
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
import type { FoodTextAnalyzeResponse } from "@/api/types";
import { getAllFoods } from "@/db/repositories/foodRepository";
import { addLogs, type NewFoodLog } from "@/db/repositories/logRepository";
import { useAuth } from "@/features/auth/AuthContext";
import { resolveFoodEntity, type ResolvedFoodEntity } from "@/features/ai/foodTextAnalysis";
import type { MealType } from "@/types/log";
import { getToday } from "@/utils/date";
import { round } from "@/utils/number";

const EXAMPLES = [
  "早餐吃了1碗米饭和2个鸡蛋",
  "午餐200克鸡胸肉，100克西兰花",
  "下午加餐一根香蕉和一杯牛奶",
];

export default function AiAddScreen() {
  const { apiRequest, status } = useAuth();
  const [text, setText] = useState("");
  const [analysis, setAnalysis] = useState<FoodTextAnalyzeResponse | null>(null);
  const [resolved, setResolved] = useState<ResolvedFoodEntity[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);

  const canSave = useMemo(
    () => resolved.length > 0 && resolved.every((item) => item.food && item.nutrition),
    [resolved]
  );

  const analyze = async () => {
    const input = text.trim();
    if (input.length < 2) {
      Alert.alert("请补充描述", "例如：午餐吃了200克鸡胸肉和一碗米饭。");
      return;
    }
    if (status === "offline") {
      Alert.alert("当前处于离线模式", "AI 解析需要连接后端，仍可返回上一页使用手动记录。");
      return;
    }
    setAnalyzing(true);
    setAnalysis(null);
    setResolved([]);
    try {
      const response = await apiRequest<FoodTextAnalyzeResponse>("/api/v1/ai/food-text:analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input, log_date: getToday(), locale: "zh-CN" }),
      });
      const foods = await getAllFoods();
      setAnalysis(response);
      setResolved(response.entities.map((entity) => resolveFoodEntity(entity, foods)));
    } catch {
      Alert.alert("解析失败", "后端暂时不可用。你的原始描述没有丢失，可以稍后重试或手动记录。");
    } finally {
      setAnalyzing(false);
    }
  };

  const confirmAndSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      const logs = resolved.flatMap<NewFoodLog>((item) => {
        if (!item.food || !item.nutrition) return [];
        return [
          {
            date: getToday(),
            mealType: item.entity.meal_type as MealType,
            foodItemId: item.food.id,
            customName: item.food.name,
            amount: item.entity.amount,
            unit: item.entity.unit,
            kcal: item.nutrition.kcal,
            protein: item.nutrition.protein,
            fat: item.nutrition.fat,
            carbs: item.nutrition.carbs,
            sugar: item.nutrition.sugar,
            sodium: item.nutrition.sodium,
            caffeine: item.nutrition.caffeine,
            note: `AI 草稿已确认：${text.trim()}`,
          },
        ];
      });
      await addLogs(logs);
      router.replace("/(tabs)");
    } catch {
      Alert.alert("保存失败", "本次草稿没有写入，请检查后重试。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#263238" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>AI 自然语言记录</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.noticeCard}>
          <Ionicons name="shield-checkmark-outline" size={22} color="#1565C0" />
          <Text style={styles.noticeText}>
            AI 只生成可编辑草稿；营养值由本地食品库计算，确认前不会写入正式记录。
          </Text>
        </View>

        <Text style={styles.label}>描述你吃了什么</Text>
        <TextInput
          accessibilityLabel="饮食自然语言描述"
          style={styles.input}
          multiline
          maxLength={1000}
          placeholder="例如：午餐吃了200克鸡胸肉、1碗米饭和100克西兰花"
          placeholderTextColor="#9E9E9E"
          value={text}
          onChangeText={(value) => {
            setText(value);
            setAnalysis(null);
            setResolved([]);
          }}
        />
        <View style={styles.examples}>
          {EXAMPLES.map((example) => (
            <TouchableOpacity
              key={example}
              style={styles.exampleChip}
              onPress={() => setText(example)}
            >
              <Text style={styles.exampleText}>{example}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          accessibilityRole="button"
          style={[styles.analyzeButton, analyzing && styles.disabled]}
          disabled={analyzing}
          onPress={analyze}
        >
          {analyzing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="sparkles" size={19} color="#fff" />
              <Text style={styles.analyzeText}>生成待确认草稿</Text>
            </>
          )}
        </TouchableOpacity>

        {analysis && (
          <View style={styles.resultSection}>
            <View style={styles.resultHeader}>
              <Text style={styles.resultTitle}>识别结果 · {resolved.length} 项</Text>
              <Text style={styles.providerBadge}>
                {analysis.fallback_used
                  ? "规则降级结果"
                  : analysis.provider.startsWith("openai")
                    ? "OpenAI"
                    : "本地演示 Provider"}
              </Text>
            </View>
            <Text style={styles.providerMeta}>
              {analysis.model} · {analysis.latency_ms} ms · {analysis.usage.total_tokens} tokens
              {analysis.usage.estimated_cost_usd !== null
                ? ` · 约 $${analysis.usage.estimated_cost_usd}`
                : ""}
            </Text>

            {(analysis.warnings ?? []).map((warning) => (
              <Text key={warning} style={styles.warning}>
                • {warning}
              </Text>
            ))}

            {resolved.map((item, index) => (
              <View key={`${item.entity.normalized_name}-${index}`} style={styles.foodCard}>
                <View style={styles.foodTitleRow}>
                  <Text style={styles.foodName}>{item.entity.normalized_name}</Text>
                  <Text
                    style={[styles.confidence, item.entity.needs_review && styles.confidenceReview]}
                  >
                    置信度 {Math.round(item.entity.confidence * 100)}%
                  </Text>
                </View>
                <Text style={styles.foodMeta}>
                  {item.entity.amount} {item.entity.unit} · {item.entity.evidence}
                </Text>
                {item.issue ? (
                  <Text style={styles.issue}>{item.issue}</Text>
                ) : (
                  <View style={styles.nutritionRow}>
                    <Text style={styles.nutritionStrong}>{round(item.nutrition!.kcal)} kcal</Text>
                    <Text style={styles.nutritionText}>
                      蛋白质 {round(item.nutrition!.protein, 1)}g
                    </Text>
                    <Text style={styles.nutritionText}>脂肪 {round(item.nutrition!.fat, 1)}g</Text>
                    <Text style={styles.nutritionText}>
                      碳水 {round(item.nutrition!.carbs, 1)}g
                    </Text>
                  </View>
                )}
              </View>
            ))}

            {resolved.length === 0 && (
              <View style={styles.emptyResult}>
                <Text style={styles.emptyText}>暂未识别出可记录食物，请换一种描述方式。</Text>
              </View>
            )}

            <TouchableOpacity
              style={[styles.saveButton, (!canSave || saving) && styles.disabled]}
              disabled={!canSave || saving}
              onPress={confirmAndSave}
            >
              <Text style={styles.saveText}>{saving ? "正在保存…" : "确认无误并保存"}</Text>
            </TouchableOpacity>
            <Text style={styles.confirmHint}>点击保存即代表你已检查食物、份量和营养估算。</Text>
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F5F7F6" },
  header: {
    paddingTop: 48,
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: "#fff",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  backButton: { padding: 4 },
  headerTitle: { fontSize: 18, fontWeight: "700", color: "#263238" },
  headerSpacer: { width: 32 },
  content: { padding: 16, paddingBottom: 40 },
  noticeCard: {
    flexDirection: "row",
    gap: 10,
    backgroundColor: "#E3F2FD",
    borderRadius: 12,
    padding: 14,
    marginBottom: 18,
  },
  noticeText: { flex: 1, color: "#37474F", fontSize: 13, lineHeight: 19 },
  label: { fontSize: 16, fontWeight: "700", color: "#263238", marginBottom: 8 },
  input: {
    minHeight: 118,
    borderRadius: 14,
    backgroundColor: "#fff",
    padding: 14,
    fontSize: 15,
    lineHeight: 22,
    color: "#263238",
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: "#E0E5E3",
  },
  examples: { gap: 8, marginTop: 10 },
  exampleChip: { alignSelf: "flex-start", backgroundColor: "#ECEFF1", padding: 8, borderRadius: 8 },
  exampleText: { color: "#546E7A", fontSize: 12 },
  analyzeButton: {
    marginTop: 16,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#2E7D32",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  analyzeText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  disabled: { opacity: 0.45 },
  resultSection: { marginTop: 24 },
  resultHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  resultTitle: { fontSize: 18, fontWeight: "700", color: "#263238" },
  providerBadge: {
    fontSize: 11,
    color: "#6A1B9A",
    backgroundColor: "#F3E5F5",
    padding: 6,
    borderRadius: 6,
  },
  providerMeta: { color: "#78909C", fontSize: 11, marginTop: 6 },
  warning: { color: "#E65100", fontSize: 12, lineHeight: 18, marginTop: 8 },
  foodCard: { backgroundColor: "#fff", padding: 14, borderRadius: 12, marginTop: 12 },
  foodTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  foodName: { flex: 1, fontSize: 16, fontWeight: "700", color: "#263238" },
  confidence: {
    color: "#2E7D32",
    backgroundColor: "#E8F5E9",
    padding: 5,
    borderRadius: 5,
    fontSize: 11,
  },
  confidenceReview: { color: "#E65100", backgroundColor: "#FFF3E0" },
  foodMeta: { color: "#607D8B", fontSize: 12, lineHeight: 18, marginTop: 6 },
  nutritionRow: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10 },
  nutritionStrong: { color: "#2E7D32", fontWeight: "700", fontSize: 13 },
  nutritionText: { color: "#546E7A", fontSize: 13 },
  issue: { color: "#C62828", fontSize: 12, marginTop: 8 },
  emptyResult: { padding: 20, alignItems: "center" },
  emptyText: { color: "#78909C", textAlign: "center" },
  saveButton: {
    marginTop: 18,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#1565C0",
    alignItems: "center",
    justifyContent: "center",
  },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  confirmHint: { textAlign: "center", color: "#90A4AE", fontSize: 11, marginTop: 8 },
});
