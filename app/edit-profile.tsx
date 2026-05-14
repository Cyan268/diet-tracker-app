import { View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView, Alert } from "react-native";
import { router } from "expo-router";
import { useState, useEffect } from "react";
import { Ionicons } from "@expo/vector-icons";
import { getProfile, upsertProfile } from "../src/db/repositories/profileRepository";
import type { Gender, ActivityLevel, Goal } from "../src/types/profile";

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
  { key: "lose", label: "减脂", desc: "每日减少500kcal摄入" },
  { key: "maintain", label: "维持", desc: "保持当前体重" },
  { key: "gain", label: "增肌", desc: "每日增加300kcal摄入" },
];

export default function EditProfileScreen() {
  const [gender, setGender] = useState<Gender>("male");
  const [age, setAge] = useState("");
  const [height, setHeight] = useState("");
  const [weight, setWeight] = useState("");
  const [activityLevel, setActivityLevel] = useState<ActivityLevel>("moderate");
  const [goal, setGoal] = useState<Goal>("maintain");
  const [saving, setSaving] = useState(false);

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

    if (!ageNum || ageNum < 10 || ageNum > 120) {
      Alert.alert("提示", "请输入有效年龄（10-120）");
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
    } catch (e) {
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
        <Text style={styles.sectionTitle}>性别</Text>
        <View style={styles.optionRow}>
          {GENDER_OPTIONS.map((opt) => (
            <TouchableOpacity
              key={opt.key}
              style={[styles.optionChip, gender === opt.key && styles.optionChipActive]}
              onPress={() => setGender(opt.key)}
            >
              <Text style={[styles.optionChipText, gender === opt.key && styles.optionChipTextActive]}>
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
              <Text style={[styles.listItemLabel, activityLevel === opt.key && styles.listItemLabelActive]}>
                {opt.label}
              </Text>
              <Text style={styles.listItemDesc}>{opt.desc}</Text>
            </View>
            {activityLevel === opt.key && <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />}
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
