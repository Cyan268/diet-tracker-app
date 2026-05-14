import { View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput, Alert } from "react-native";
import { router } from "expo-router";
import { useState, useEffect, useCallback } from "react";
import { Ionicons } from "@expo/vector-icons";
import { getBrands, getDrinkNames, getOptionsWithFallback } from "../src/db/repositories/drinkOptionRepository";
import { addLog } from "../src/db/repositories/logRepository";
import { calcDrink } from "../src/features/drink/drinkCalculator";
import { getToday } from "../src/utils/date";
import { round } from "../src/utils/number";
import type { DrinkOption } from "../src/types/drink";

export default function AddDrinkScreen() {
  const [brands, setBrands] = useState<string[]>([]);
  const [drinkNames, setDrinkNames] = useState<string[]>([]);
  const [sizeOptions, setSizeOptions] = useState<DrinkOption[]>([]);
  const [sugarOptions, setSugarOptions] = useState<DrinkOption[]>([]);
  const [milkOptions, setMilkOptions] = useState<DrinkOption[]>([]);
  const [toppingOptions, setToppingOptions] = useState<DrinkOption[]>([]);

  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [selectedDrink, setSelectedDrink] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<DrinkOption | null>(null);
  const [selectedSugar, setSelectedSugar] = useState<DrinkOption | null>(null);
  const [selectedMilk, setSelectedMilk] = useState<DrinkOption | null>(null);
  const [selectedToppings, setSelectedToppings] = useState<DrinkOption[]>([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getBrands().then(setBrands);
  }, []);

  useEffect(() => {
    if (selectedBrand) {
      getDrinkNames(selectedBrand).then((names) => {
        setDrinkNames(names);
        setSelectedDrink(null);
        setSelectedSize(null);
        setSelectedSugar(null);
        setSelectedMilk(null);
        setSelectedToppings([]);
      });
    }
  }, [selectedBrand]);

  useEffect(() => {
    if (selectedBrand && selectedDrink) {
      Promise.all([
        getOptionsWithFallback(selectedBrand, selectedDrink, "size"),
        getOptionsWithFallback(selectedBrand, selectedDrink, "sugar"),
        getOptionsWithFallback(selectedBrand, selectedDrink, "milk"),
        getOptionsWithFallback(selectedBrand, selectedDrink, "topping"),
      ]).then(([sizes, sugars, milks, toppings]) => {
        setSizeOptions(sizes);
        setSugarOptions(sugars);
        setMilkOptions(milks);
        setToppingOptions(toppings);
        setSelectedSize(sizes[0] ?? null);
        setSelectedSugar(sugars[0] ?? null);
        setSelectedMilk(null);
        setSelectedToppings([]);
      });
    }
  }, [selectedBrand, selectedDrink]);

  const toggleTopping = (opt: DrinkOption) => {
    setSelectedToppings((prev) => {
      const exists = prev.find((t) => t.id === opt.id);
      return exists ? prev.filter((t) => t.id !== opt.id) : [...prev, opt];
    });
  };

  const otherOptions = [selectedSugar, selectedMilk, ...selectedToppings].filter(Boolean) as DrinkOption[];
  const calcResult = selectedSize ? calcDrink(selectedSize, otherOptions) : null;

  const handleSave = async () => {
    if (!selectedSize || !selectedBrand || !selectedDrink) {
      Alert.alert("提示", "请选择品牌、饮品和杯型");
      return;
    }
    setSaving(true);
    try {
      const drinkName = `${selectedBrand} ${selectedDrink}`;
      const optNames = [
        selectedSize.optionName,
        selectedSugar?.optionName,
        selectedMilk?.optionName,
        ...selectedToppings.map((t) => t.optionName),
      ].filter(Boolean);
      await addLog({
        date: getToday(),
        mealType: "drink",
        customName: `${drinkName}（${optNames.join("、")}）`,
        amount: 1,
        unit: "杯",
        kcal: calcResult!.kcal,
        protein: 0,
        fat: 0,
        carbs: 0,
        sugar: calcResult!.sugar,
        sodium: 0,
        caffeine: calcResult!.caffeine,
        note: note || undefined,
      });
      router.back();
    } catch (e) {
      Alert.alert("错误", "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  const renderOptionGroup = (
    title: string,
    options: DrinkOption[],
    selected: DrinkOption | null,
    onSelect: (opt: DrinkOption) => void
  ) => (
    <View style={styles.group}>
      <Text style={styles.groupTitle}>{title}</Text>
      <View style={styles.optionRow}>
        {options.map((opt) => (
          <TouchableOpacity
            key={opt.id}
            style={[styles.optionChip, selected?.id === opt.id && styles.optionChipActive]}
            onPress={() => onSelect(opt)}
          >
            <Text style={[styles.optionChipText, selected?.id === opt.id && styles.optionChipTextActive]}>
              {opt.optionName}
            </Text>
          </TouchableOpacity>
        ))}
        {options.length === 0 && <Text style={styles.noOption}>暂无选项</Text>}
      </View>
    </View>
  );

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>添加饮品</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.groupTitle}>品牌</Text>
        <View style={styles.optionRow}>
          {brands.map((b) => (
            <TouchableOpacity
              key={b}
              style={[styles.optionChip, selectedBrand === b && styles.optionChipActive]}
              onPress={() => setSelectedBrand(b)}
            >
              <Text style={[styles.optionChipText, selectedBrand === b && styles.optionChipTextActive]}>{b}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {selectedBrand && (
        <View style={styles.section}>
          <Text style={styles.groupTitle}>饮品</Text>
          <View style={styles.optionRow}>
            {drinkNames.map((d) => (
              <TouchableOpacity
                key={d}
                style={[styles.optionChip, selectedDrink === d && styles.optionChipActive]}
                onPress={() => setSelectedDrink(d)}
              >
                <Text style={[styles.optionChipText, selectedDrink === d && styles.optionChipTextActive]}>{d}</Text>
              </TouchableOpacity>
            ))}
            {drinkNames.length === 0 && <Text style={styles.noOption}>暂无饮品</Text>}
          </View>
        </View>
      )}

      {selectedDrink && (
        <>
          {renderOptionGroup("杯型", sizeOptions, selectedSize, setSelectedSize)}
          {renderOptionGroup("糖度", sugarOptions, selectedSugar, setSelectedSugar)}
          {renderOptionGroup("奶基", milkOptions, selectedMilk, setSelectedMilk)}

          <View style={styles.group}>
            <Text style={styles.groupTitle}>小料（可多选）</Text>
            <View style={styles.optionRow}>
              {toppingOptions.map((t) => {
                const active = selectedToppings.some((s) => s.id === t.id);
                return (
                  <TouchableOpacity
                    key={t.id}
                    style={[styles.optionChip, active && styles.optionChipActive]}
                    onPress={() => toggleTopping(t)}
                  >
                    <Text style={[styles.optionChipText, active && styles.optionChipTextActive]}>{t.optionName}</Text>
                  </TouchableOpacity>
                );
              })}
              {toppingOptions.length === 0 && <Text style={styles.noOption}>暂无小料</Text>}
            </View>
          </View>

          <TextInput
            style={styles.noteInput}
            placeholder="备注（可选）"
            value={note}
            onChangeText={setNote}
          />

          {calcResult && (
            <View style={styles.preview}>
              <Text style={styles.previewTitle}>预计摄入</Text>
              <View style={styles.previewGrid}>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(calcResult.kcal)}</Text>
                  <Text style={styles.previewLabel}>热量(kcal)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(calcResult.sugar, 1)}</Text>
                  <Text style={styles.previewLabel}>糖(g)</Text>
                </View>
                <View style={styles.previewItem}>
                  <Text style={styles.previewValue}>{round(calcResult.caffeine)}</Text>
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
            <Text style={styles.saveBtnText}>{saving ? "保存中..." : "保存饮品"}</Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
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
  section: { backgroundColor: "#fff", marginHorizontal: 16, marginTop: 12, padding: 14, borderRadius: 12 },
  group: { backgroundColor: "#fff", marginHorizontal: 16, marginTop: 12, padding: 14, borderRadius: 12 },
  groupTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 10 },
  optionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  optionChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: "#f5f5f5",
    borderWidth: 1,
    borderColor: "#e0e0e0",
  },
  optionChipActive: { backgroundColor: "#E8F5E9", borderColor: "#4CAF50" },
  optionChipText: { fontSize: 13, color: "#666" },
  optionChipTextActive: { color: "#4CAF50", fontWeight: "600" },
  noOption: { fontSize: 13, color: "#ccc" },
  noteInput: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 14,
    color: "#333",
  },
  preview: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 14,
  },
  previewTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 10 },
  previewGrid: { flexDirection: "row", justifyContent: "space-around", marginBottom: 4 },
  previewItem: { alignItems: "center" },
  previewValue: { fontSize: 20, fontWeight: "bold", color: "#4CAF50" },
  previewLabel: { fontSize: 11, color: "#999", marginTop: 2 },
  saveBtn: {
    backgroundColor: "#4CAF50",
    marginHorizontal: 16,
    marginTop: 16,
    marginBottom: 40,
    borderRadius: 12,
    height: 48,
    justifyContent: "center",
    alignItems: "center",
  },
  saveBtnDisabled: { opacity: 0.6 },
  saveBtnText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
