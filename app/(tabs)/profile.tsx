import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";

const menuItems = [
  { icon: "person-outline" as const, label: "个人资料", desc: "性别、年龄、身高、体重" },
  { icon: "flag-outline" as const, label: "目标设置", desc: "减脂 / 维持 / 增肌" },
  { icon: "notifications-outline" as const, label: "提醒设置", desc: "热量、糖、咖啡因提醒" },
  { icon: "download-outline" as const, label: "数据导出", desc: "导出饮食记录" },
  { icon: "information-circle-outline" as const, label: "关于", desc: "版本信息与免责声明" },
];

export default function ProfileScreen() {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={40} color="#fff" />
        </View>
        <Text style={styles.username}>用户</Text>
        <Text style={styles.desc}>记录健康饮食，享受美好生活</Text>
      </View>

      <View style={styles.menuList}>
        {menuItems.map((item, index) => (
          <TouchableOpacity key={index} style={styles.menuItem}>
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
  container: {
    flex: 1,
    backgroundColor: "#f5f5f5",
  },
  header: {
    backgroundColor: "#4CAF50",
    padding: 30,
    alignItems: "center",
  },
  avatar: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: "rgba(255,255,255,0.3)",
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 10,
  },
  username: {
    fontSize: 20,
    fontWeight: "bold",
    color: "#fff",
  },
  desc: {
    fontSize: 13,
    color: "rgba(255,255,255,0.8)",
    marginTop: 4,
  },
  menuList: {
    backgroundColor: "#fff",
    marginTop: 16,
    marginHorizontal: 16,
    borderRadius: 12,
    overflow: "hidden",
  },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderBottomWidth: 0.5,
    borderBottomColor: "#f0f0f0",
  },
  menuLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  menuText: {},
  menuLabel: {
    fontSize: 15,
    fontWeight: "500",
    color: "#333",
  },
  menuDesc: {
    fontSize: 12,
    color: "#999",
    marginTop: 2,
  },
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
