import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, Alert, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useLocalSearchParams, router } from "expo-router";
import { useState, useCallback, useRef, useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { searchAllFoods } from "../src/services/foodSearchService";
import { saveExternalFood } from "../src/db/repositories/foodRepository";
import { addLog } from "../src/db/repositories/logRepository";
import { calcByGram } from "../src/features/food/foodCalculator";
import { getToday } from "../src/utils/date";
import { round } from "../src/utils/number";
import type { FoodItem } from "../src/types/nutrition";
import type { ExternalFoodResult } from "../src/types/external";
import type { MealType } from "../src/types/log";

const MEAL_LABELS: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
};

export default function AddFoodScreen() {
  const { mealType } = useLocalSearchParams<{ mealType: string }>();
  const mt = (mealType ?? "breakfast") as MealType;

  const [keyword, setKeyword] = useState("");
  const [localResults, setLocalResults] = useState<FoodItem[]>([]);
  const [externalResults, setExternalResults] = useState<ExternalFoodResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<FoodItem | null>(null);
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("g");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, []);

  const handleSearch = useCallback((text: string) => {
    setKeyword(text);
    setSelected(null);

    if (searchTimer.current) clearTimeout(searchTimer.current);

    if (text.trim().length === 0) {
      setLocalResults([]);
      setExternalResults([]);
      return;
    }

    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await searchAllFoods(text);
        setLocalResults(results.local);
        setExternalResults(results.external);
      } catch {
        setLocalResults([]);
        setExternalResults([]);
      } finally {
        setSearching(false);
      }
    }, 400);
  }, []);

  const handleSelectLocal = (food: FoodItem) => {
    setSelected(food);
    setLocalResults([]);
    setExternalResults([]);
    setKeyword(food.name);
    if (food.servingUnit && food.servingWeightG) {
      setUnit(food.servingUnit);
      setAmount("1");
    } else {
      setUnit("g");
      setAmount("");
    }
  };

  const handleSelectExternal = async (result: ExternalFoodResult) => {
    setSearching(true);
    try {
      const cached = await saveExternalFood(result);
      handleSelectLocal(cached);
    } catch {
      Alert.alert("错误", "保存食物数据失败，请重试");
    } finally {
      setSearching(false);
    }
  };

  const clearSearch = () => {
    setKeyword("");
    setLocalResults([]);
    setExternalResults([]);
    setSelected(null);
    setAmount("");
    if (searchTimer.current) clearTimeout(searchTimer.current);
  };

  const getGrams = (): number => {
    if (!selected) return 0;
    if (unit === "g") return parseFloat(amount) || 0;
    if (selected.servingWeightG) {
      return (parseFloat(amount) || 0) * selected.servingWeightG;
    }
    return parseFloat(amount) || 0;
  };

  const grams = getGrams();
  const nutrition = selected ? calcByGram(selected, grams) : null;

  const handleSave = async () => {
    if (!selected || grams <= 0) {
      Alert.alert("提示", "请选择食物并输入数量");
      return;
    }
    setSaving(true);
    try {
      await addLog({
        date: getToday(),
        mealType: mt,
        foodItemId: selected.id,
        customName: selected.name,
        amount: parseFloat(amount) || 0,
        unit,
        kcal: nutrition!.kcal,
        protein: nutrition!.protein,
        fat: nutrition!.fat,
        carbs: nutrition!.carbs,
        sugar: nutrition!.sugar,
        sodium: nutrition!.sodium,
        caffeine: nutrition!.caffeine,
        note: note || undefined,
      });
      router.back();
    } catch (e) {
      Alert.alert("错误", "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  const hasResults = localResults.length > 0 || externalResults.length > 0;
  const showNoResults = keyword.length > 0 && !searching && !hasResults && !selected;

  const renderLocalItem = ({ item }: { item: FoodItem }) => (
    <TouchableOpacity style={styles.resultItem} onPress={() => handleSelectLocal(item)}>
      <View style={styles.resultContent}>
        <Text style={styles.resultName}>{item.name}</Text>
        <Text style={styles.resultMeta}>
          {item.category ?? ""} · {round(item.kcalPer100g)} kcal/100g
        </Text>
      </View>
      <Text style={styles.badgeLocal}>本地</Text>
      <Ionicons name="chevron-forward" size={18} color="#ccc" />
    </TouchableOpacity>
  );

  const renderExternalItem = ({ item }: { item: ExternalFoodResult }) => (
    <TouchableOpacity style={styles.resultItem} onPress={() => handleSelectExternal(item)}>
      <View style={styles.resultContent}>
        <Text style={styles.resultName}>{item.name}</Text>
        <Text style={styles.resultMeta}>
          {item.brand ? `${item.brand} · ` : ""}{round(item.kcalPer100g)} kcal/100g
        </Text>
      </View>
      <Text style={styles.badgeExternal}>网络</Text>
      <Ionicons name="chevron-forward" size={18} color="#ccc" />
    </TouchableOpacity>
  );

  // Build combined list with section headers
  const combinedData: (
    | { type: "local"; item: FoodItem }
    | { type: "external"; item: ExternalFoodResult }
    | { type: "header"; label: string }
  )[] = [];
  if (localResults.length > 0) {
    combinedData.push({ type: "header", label: "本地食物" });
    for (const item of localResults) combinedData.push({ type: "local", item });
  }
  if (externalResults.length > 0) {
    combinedData.push({ type: "header", label: "网络搜索结果" });
    for (const item of externalResults) combinedData.push({ type: "external", item });
  }

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>添加{MEAL_LABELS[mt] ?? "食物"}</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.searchBox}>
        <Ionicons name="search" size={20} color="#999" />
        <TextInput
          style={styles.searchInput}
          placeholder="搜索食物名称..."
          value={keyword}
          onChangeText={handleSearch}
          autoFocus
        />
        {searching && <ActivityIndicator size="small" color="#4CAF50" style={{ marginRight: 4 }} />}
        {keyword.length > 0 && !searching && (
          <TouchableOpacity onPress={clearSearch}>
            <Ionicons name="close-circle" size={20} color="#999" />
          </TouchableOpacity>
        )}
      </View>

      {showNoResults && (
        <View style={styles.noResults}>
          <Ionicons name="search-outline" size={32} color="#e0e0e0" />
          <Text style={styles.noResultsText}>未找到「{keyword}」</Text>
          <Text style={styles.noResultsHint}>试试其他关键词</Text>
        </View>
      )}

      {combinedData.length > 0 && !selected && (
        <FlatList
          data={combinedData}
          keyExtractor={(item, index) =>
            item.type === "header" ? `header-${(item as any).label}` : (item as any).item.id ?? `ext-${index}`
          }
          style={styles.resultList}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item }) => {
            if (item.type === "header") {
              return <Text style={styles.sectionHeader}>{(item as any).label}</Text>;
            }
            if (item.type === "local") {
              return renderLocalItem({ item: (item as any).item });
            }
            return renderExternalItem({ item: (item as any).item });
          }}
        />
      )}

      {selected && (
        <View style={styles.detailArea}>
          <View style={styles.selectedFood}>
            <Text style={styles.selectedName}>{selected.name}</Text>
            <Text style={styles.selectedMeta}>{selected.category ?? ""}</Text>
          </View>

          <View style={styles.amountRow}>
            <TextInput
              style={styles.amountInput}
              placeholder="数量"
              keyboardType="numeric"
              value={amount}
              onChangeText={setAmount}
            />
            <TouchableOpacity
              style={styles.unitBtn}
              onPress={() => {
                if (selected.servingUnit && selected.servingWeightG) {
                  setUnit(unit === "g" ? selected.servingUnit : "g");
                }
              }}
            >
              <Text style={styles.unitText}>{unit}</Text>
              {selected.servingUnit && selected.servingWeightG && (
                <Ionicons name="swap-horizontal" size={16} color="#4CAF50" />
              )}
            </TouchableOpacity>
          </View>

          {unit !== "g" && selected.servingWeightG && (
            <Text style={styles.gramHint}>
              ≈ {round(grams)}g
            </Text>
          )}

          <TextInput
            style={styles.noteInput}
            placeholder="备注（可选）"
            value={note}
            onChangeText={setNote}
          />

          {nutrition && grams > 0 && (
            <View style={styles.preview}>
              <Text style={styles.previewTitle}>营养素预览</Text>
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
              <View style={styles.previewGrid}>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.sugar, 1)}</Text>
                  <Text style={styles.previewLabel}>糖(g)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.sodium)}</Text>
                  <Text style={styles.previewLabel}>钠(mg)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(nutrition.caffeine)}</Text>
                  <Text style={styles.previewLabel}>咖啡因(mg)</Text>
                </View>
              </View>
            </View>
          )}

          <TouchableOpacity
            style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={saving}
          >
            <Text style={styles.saveBtnText}>{saving ? "保存中..." : "保存记录"}</Text>
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
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
  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 16,
    paddingHorizontal: 12,
    borderRadius: 10,
    height: 44,
  },
  searchInput: { flex: 1, marginLeft: 8, fontSize: 15, color: "#333" },
  noResults: {
    alignItems: "center",
    paddingVertical: 30,
    marginHorizontal: 16,
  },
  noResultsText: {
    fontSize: 15,
    fontWeight: "500",
    color: "#999",
    marginTop: 10,
  },
  noResultsHint: {
    fontSize: 12,
    color: "#bbb",
    marginTop: 4,
  },
  resultList: { marginHorizontal: 16, marginTop: 4 },
  sectionHeader: {
    fontSize: 12,
    fontWeight: "600",
    color: "#999",
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 6,
  },
  resultItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    padding: 12,
    borderBottomWidth: 0.5,
    borderBottomColor: "#f0f0f0",
  },
  resultContent: { flex: 1 },
  resultName: { fontSize: 15, fontWeight: "500", color: "#333" },
  resultMeta: { fontSize: 12, color: "#999", marginTop: 2 },
  badgeLocal: {
    fontSize: 10,
    color: "#4CAF50",
    backgroundColor: "#E8F5E9",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: "hidden",
    marginRight: 6,
  },
  badgeExternal: {
    fontSize: 10,
    color: "#2196F3",
    backgroundColor: "#E3F2FD",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: "hidden",
    marginRight: 6,
  },
  detailArea: { flex: 1, padding: 16 },
  selectedFood: { marginBottom: 12 },
  selectedName: { fontSize: 18, fontWeight: "600", color: "#333" },
  selectedMeta: { fontSize: 13, color: "#999", marginTop: 2 },
  amountRow: { flexDirection: "row", gap: 8, marginBottom: 8 },
  amountInput: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 16,
    color: "#333",
  },
  unitBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    gap: 4,
  },
  unitText: { fontSize: 15, color: "#4CAF50", fontWeight: "600" },
  gramHint: { fontSize: 12, color: "#999", marginBottom: 8, marginLeft: 4 },
  noteInput: {
    backgroundColor: "#fff",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 14,
    color: "#333",
    marginBottom: 12,
  },
  preview: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  previewTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 10 },
  previewGrid: { flexDirection: "row", justifyContent: "space-around", marginBottom: 8 },
  previewItem: { alignItems: "center" },
  previewValue: { fontSize: 16, fontWeight: "bold", color: "#4CAF50" },
  previewLabel: { fontSize: 11, color: "#999", marginTop: 2 },
  saveBtn: {
    backgroundColor: "#4CAF50",
    borderRadius: 12,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
