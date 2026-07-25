import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  Alert,
} from "react-native";
import { router } from "expo-router";
import { useState, useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { getProfile, upsertProfile } from "../src/db/repositories/profileRepository";
import type { Gender, ActivityLevel, Goal, UserProfile } from "../src/types/profile";
import { calcProfileMetrics } from "../src/features/profile/profileCalculator";

const GENDER_OPTIONS: { key: Gender; label: string }[] = [
  { key: "male", label: "男" },
  { key: "female", label: "女" },
];

const ACTIVITY_OPTIONS: { key: ActivityLevel; label: string; desc: string }[] = [
  { key: "sedentary", label: "久坐", desc: "办公室、很少运动" },
  { key: "light", label: "轻度活动", desc: "每周运动1-3次" },
  { key: "moderate", label: "中度活动", desc: "每周运动3-5次" },
  { key: "active", label: "高度活动", desc: "每周运动6-7次" },
  { key: "very_active", label: "极高活动", desc: "体力劳动或每天高强度训练" },
];

const GOAL_OPTIONS: { key: Goal; label: string; desc: string }[] = [
  { key: "lose", label: "减脂", desc: "在估算消耗基础上每日减少 500 kcal" },
  { key: "maintain", label: "维持", desc: "保持当前体重" },
  { key: "gain", label: "增肌", desc: "在估算消耗基础上每日增加 300 kcal" },
];

export default function EditProfileScreen() {
  const [gender, setGender] = useState<Gender>("male");
  const [age, setAge] = useState("");
  const [height, setHeight] = useState("");
  const [weight, setWeight] = useState("");
  const [activityLevel, setActivityLevel] = useState<ActivityLevel>("moderate");
  const [goal, setGoal] = useState<Goal>("maintain");
  const [saving, setSaving] = useState(false);
  const ageNumber = Number(age);
  const heightNumber = Number(height);
  const weightNumber = Number(weight);
  const previewProfile: UserProfile | null =
    ageNumber >= 18 &&
    ageNumber <= 100 &&
    heightNumber >= 100 &&
    heightNumber <= 250 &&
    weightNumber >= 30 &&
    weightNumber <= 200
      ? {
          id: "preview",
          gender,
          age: ageNumber,
          heightCm: heightNumber,
          weightKg: weightNumber,
          activityLevel,
          goal,
          createdAt: "",
          updatedAt: "",
        }
      : null;
  const preview = previewProfile ? calcProfileMetrics(previewProfile) : null;

  useEffect(() => {
    getProfile().then((p) => {
      if (p) {
        setGender(p.gender);
        setAge(String(p.age));
        setHeight(String(p.heightCm));
        setWeight(String(p.weightKg));
        setActivityLevel(p.activityLevel);
        setGoal(p.goal);
      }
    });
  }, []);

  const handleSave = async () => {
    const ageNum = parseInt(age);
    const heightNum = parseFloat(height);
    const weightNum = parseFloat(weight);

    if (!ageNum || ageNum < 18 || ageNum > 100) {
      Alert.alert("提示", "当前版本面向成年人，请输入有效年龄（18-100）");
      return;
    }
    if (!heightNum || heightNum < 100 || heightNum > 250) {
      Alert.alert("提示", "请输入有效身高（100-250 cm）");
      return;
    }
    if (!weightNum || weightNum < 30 || weightNum > 200) {
      Alert.alert("提示", "请输入有效体重（30-200 kg）");
      return;
    }

    setSaving(true);
    try {
      await upsertProfile({
        gender,
        age: ageNum,
        heightCm: heightNum,
        weightKg: weightNum,
        activityLevel,
        goal,
      });
      router.back();
    } catch {
      Alert.alert("错误", "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#333" />
        </TouchableOpacity>
        <Text style={styles.title}>个人资料</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>生理性别（用于代谢公式）</Text>
        <View style={styles.optionRow}>
          {GENDER_OPTIONS.map((opt) => (
            <TouchableOpacity
              key={opt.key}
              style={[styles.optionChip, gender === opt.key && styles.optionChipActive]}
              onPress={() => setGender(opt.key)}
            >
              <Text
                style={[styles.optionChipText, gender === opt.key && styles.optionChipTextActive]}
              >
                {opt.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>年龄</Text>
        <TextInput
          style={styles.input}
          placeholder="请输入年龄"
          keyboardType="numeric"
          value={age}
          onChangeText={setAge}
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>身高 (cm)</Text>
        <TextInput
          style={styles.input}
          placeholder="请输入身高"
          keyboardType="numeric"
          value={height}
          onChangeText={setHeight}
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>体重 (kg)</Text>
        <TextInput
          style={styles.input}
          placeholder="请输入体重"
          keyboardType="numeric"
          value={weight}
          onChangeText={setWeight}
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>活动水平</Text>
        {ACTIVITY_OPTIONS.map((opt) => (
          <TouchableOpacity
            key={opt.key}
            style={[styles.listItem, activityLevel === opt.key && styles.listItemActive]}
            onPress={() => setActivityLevel(opt.key)}
          >
            <View style={styles.listItemContent}>
              <Text
                style={[
                  styles.listItemLabel,
                  activityLevel === opt.key && styles.listItemLabelActive,
                ]}
              >
                {opt.label}
              </Text>
              <Text style={styles.listItemDesc}>{opt.desc}</Text>
            </View>
            {activityLevel === opt.key && (
              <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />
            )}
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>目标</Text>
        {GOAL_OPTIONS.map((opt) => (
          <TouchableOpacity
            key={opt.key}
            style={[styles.listItem, goal === opt.key && styles.listItemActive]}
            onPress={() => setGoal(opt.key)}
          >
            <View style={styles.listItemContent}>
              <Text style={[styles.listItemLabel, goal === opt.key && styles.listItemLabelActive]}>
                {opt.label}
              </Text>
              <Text style={styles.listItemDesc}>{opt.desc}</Text>
            </View>
            {goal === opt.key && <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />}
          </TouchableOpacity>
        ))}
      </View>

      {preview && (
        <View style={styles.previewCard}>
          <View style={styles.previewHeader}>
            <Text style={styles.previewTitle}>你的每日营养目标预览</Text>
            <Ionicons name="sparkles-outline" size={19} color="#4CAF50" />
          </View>
          <View style={styles.energyRow}>
            <View style={styles.energyItem}>
              <Text style={styles.energyValue}>{preview.bmr}</Text>
              <Text style={styles.energyLabel}>基础代谢 kcal</Text>
            </View>
            <View style={styles.energyItem}>
              <Text style={styles.energyValue}>{preview.tdee}</Text>
              <Text style={styles.energyLabel}>维持消耗 kcal</Text>
            </View>
            <View style={styles.energyItem}>
              <Text style={styles.energyValue}>{preview.bmi}</Text>
              <Text style={styles.energyLabel}>BMI</Text>
            </View>
          </View>
          <View style={styles.targetGrid}>
            <Text style={styles.targetText}>热量 {preview.targets.kcal} kcal</Text>
            <Text style={styles.targetText}>蛋白质 {preview.targets.protein} g</Text>
            <Text style={styles.targetText}>脂肪 {preview.targets.fat} g</Text>
            <Text style={styles.targetText}>碳水 {preview.targets.carbs} g</Text>
          </View>
          <Text style={styles.limitText}>
            提醒上限：添加糖 {preview.targets.sugar} g · 钠 {preview.targets.sodium} mg · 咖啡因{" "}
            {preview.targets.caffeine} mg
          </Text>
          <Text style={styles.formulaNote}>
            基于 Mifflin–St Jeor
            公式和活动系数估算，结果会有个体误差，仅用于日常记录，不替代医生或营养师建议。
          </Text>
        </View>
      )}

      <TouchableOpacity
        style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
        onPress={handleSave}
        disabled={saving}
      >
        <Text style={styles.saveBtnText}>{saving ? "保存中..." : "保存资料"}</Text>
      </TouchableOpacity>
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
  section: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 12,
    padding: 14,
    borderRadius: 12,
  },
  sectionTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 10 },
  optionRow: { flexDirection: "row", gap: 10 },
  optionChip: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: "#f5f5f5",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#e0e0e0",
  },
  optionChipActive: { backgroundColor: "#E8F5E9", borderColor: "#4CAF50" },
  optionChipText: { fontSize: 15, color: "#666" },
  optionChipTextActive: { color: "#4CAF50", fontWeight: "600" },
  input: {
    backgroundColor: "#f5f5f5",
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 15,
    color: "#333",
  },
  listItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 6,
  },
  listItemActive: { backgroundColor: "#E8F5E9" },
  listItemContent: { flex: 1 },
  listItemLabel: { fontSize: 15, fontWeight: "500", color: "#333" },
  listItemLabelActive: { color: "#4CAF50" },
  listItemDesc: { fontSize: 12, color: "#999", marginTop: 2 },
  previewCard: {
    backgroundColor: "#F1F8F2",
    marginHorizontal: 16,
    marginTop: 14,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#C8E6C9",
  },
  previewHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  previewTitle: { fontSize: 15, fontWeight: "700", color: "#2E5D32" },
  energyRow: { flexDirection: "row", marginTop: 14, gap: 8 },
  energyItem: { flex: 1, alignItems: "center" },
  energyValue: { fontSize: 19, fontWeight: "700", color: "#4CAF50" },
  energyLabel: { fontSize: 10, color: "#6B7B6D", marginTop: 3, textAlign: "center" },
  targetGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 },
  targetText: {
    width: "48%",
    fontSize: 12,
    color: "#38543B",
    backgroundColor: "#fff",
    padding: 8,
    borderRadius: 8,
  },
  limitText: { fontSize: 11, color: "#667568", lineHeight: 17, marginTop: 12 },
  formulaNote: { fontSize: 11, color: "#7A877C", lineHeight: 17, marginTop: 8 },
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
