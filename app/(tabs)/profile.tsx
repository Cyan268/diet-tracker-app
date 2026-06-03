import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useState, useCallback } from "react";
import { getProfile } from "../../src/db/repositories/profileRepository";
import { calcDailyTargets } from "../../src/features/profile/profileCalculator";
import { exportData } from "../../src/features/export/exportService";
import type { UserProfile, DailyTargets } from "../../src/types/profile";

const ACTIVITY_LABELS: Record<string, string> = {
  sedentary: "久坐",
  light: "轻度活动",
  moderate: "中度活动",
  active: "高度活动",
  very_active: "极高活动",
};

const GOAL_LABELS: Record<string, string> = {
  lose: "减脂",
  maintain: "维持",
  gain: "增肌",
};

export default function ProfileScreen() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [targets, setTargets] = useState<DailyTargets | null>(null);

  useFocusEffect(
    useCallback(() => {
      getProfile().then((p) => {
        setProfile(p);
        if (p) setTargets(calcDailyTargets(p));
      });
    }, [])
  );

  const menuItems = [
    {
      icon: "person-outline" as const,
      label: "个人资料",
      desc: profile ? `${profile.gender === "male" ? "男" : "女"} · ${profile.age}岁 · ${profile.heightCm}cm · ${profile.weightKg}kg` : "点击填写",
      onPress: () => router.push("/edit-profile"),
    },
    {
      icon: "flag-outline" as const,
      label: "目标设置",
      desc: profile ? `${GOAL_LABELS[profile.goal] ?? profile.goal} · ${ACTIVITY_LABELS[profile.activityLevel] ?? profile.activityLevel}` : "点击设置",
      onPress: () => router.push("/edit-profile"),
    },
    {
      icon: "notifications-outline" as const,
      label: "提醒设置",
      desc: "热量、糖、咖啡因提醒",
      onPress: () => router.push("/reminder-settings"),
    },
    {
      icon: "download-outline" as const,
      label: "数据导出",
      desc: "导出饮食记录",
      onPress: () => {
        Alert.alert("导出饮食记录", "选择导出格式", [
          {
            text: "CSV",
            onPress: async () => {
              try {
                await exportData("csv");
              } catch (e: any) {
                if (e.message === "NO_DATA") {
                  Alert.alert("提示", "暂无记录可导出");
                } else {
                  Alert.alert("错误", "导出失败，请重试");
                }
              }
            },
          },
          {
            text: "JSON",
            onPress: async () => {
              try {
                await exportData("json");
              } catch (e: any) {
                if (e.message === "NO_DATA") {
                  Alert.alert("提示", "暂无记录可导出");
                } else {
                  Alert.alert("错误", "导出失败，请重试");
                }
              }
            },
          },
          { text: "取消", style: "cancel" },
        ]);
      },
    },
    {
      icon: "information-circle-outline" as const,
      label: "关于",
      desc: "版本信息与免责声明",
      onPress: () =>
        Alert.alert(
          "关于",
          "日常饮食记录 v1.0.0\n\n本应用中的营养计算均为生活记录与大致估算，不构成医学、诊断或治疗建议。"
        ),
    },
  ];

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={40} color="#fff" />
        </View>
        <Text style={styles.username}>用户</Text>
        <Text style={styles.desc}>记录健康饮食，享受美好生活</Text>
      </View>

      {targets && (
        <View style={styles.targetCard}>
          <Text style={styles.targetTitle}>每日目标</Text>
          <View style={styles.targetGrid}>
            <View style={styles.targetItem}>
              <Text style={styles.targetValue}>{targets.kcal}</Text>
              <Text style={styles.targetLabel}>热量(kcal)</Text>
            </View>
            <View style={styles.targetItem}>
              <Text style={styles.targetValue}>{targets.protein}g</Text>
              <Text style={styles.targetLabel}>蛋白质</Text>
            </View>
            <View style={styles.targetItem}>
              <Text style={styles.targetValue}>{targets.fat}g</Text>
              <Text style={styles.targetLabel}>脂肪</Text>
            </View>
            <View style={styles.targetItem}>
              <Text style={styles.targetValue}>{targets.carbs}g</Text>
              <Text style={styles.targetLabel}>碳水</Text>
            </View>
          </View>
        </View>
      )}

      <View style={styles.menuList}>
        {menuItems.map((item, index) => (
          <TouchableOpacity key={index} style={styles.menuItem} onPress={item.onPress}>
            <View style={styles.menuLeft}>
              <Ionicons name={item.icon} size={22} color="#4CAF50" />
              <View style={styles.menuText}>
                <Text style={styles.menuLabel}>{item.label}</Text>
                <Text style={styles.menuDesc}>{item.desc}</Text>
              </View>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#ccc" />
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.disclaimer}>
        本应用中的营养计算均为生活记录与大致估算，不构成医学、诊断或治疗建议。
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  header: { backgroundColor: "#4CAF50", padding: 30, alignItems: "center" },
  avatar: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: "rgba(255,255,255,0.3)",
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 10,
  },
  username: { fontSize: 20, fontWeight: "bold", color: "#fff" },
  desc: { fontSize: 13, color: "rgba(255,255,255,0.8)", marginTop: 4 },
  targetCard: {
    backgroundColor: "#fff",
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    borderRadius: 12,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  targetTitle: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 12 },
  targetGrid: { flexDirection: "row", justifyContent: "space-around" },
  targetItem: { alignItems: "center" },
  targetValue: { fontSize: 18, fontWeight: "bold", color: "#4CAF50" },
  targetLabel: { fontSize: 11, color: "#999", marginTop: 2 },
  menuList: { backgroundColor: "#fff", marginTop: 16, marginHorizontal: 16, borderRadius: 12, overflow: "hidden" },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderBottomWidth: 0.5,
    borderBottomColor: "#f0f0f0",
  },
  menuLeft: { flexDirection: "row", alignItems: "center", gap: 12 },
  menuText: {},
  menuLabel: { fontSize: 15, fontWeight: "500", color: "#333" },
  menuDesc: { fontSize: 12, color: "#999", marginTop: 2 },
  disclaimer: {
    fontSize: 12,
    color: "#999",
    textAlign: "center",
    marginHorizontal: 30,
    marginTop: 24,
    marginBottom: 40,
    lineHeight: 18,
  },
});
