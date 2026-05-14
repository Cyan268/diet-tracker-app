import { View, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

interface ReminderCardProps {
  icon: keyof typeof Ionicons.glyphMap;
  message: string;
  type?: "warning" | "info";
}

export function ReminderCard({ icon, message, type = "info" }: ReminderCardProps) {
  const bgColor = type === "warning" ? "#FFF3E0" : "#E3F2FD";
  const iconColor = type === "warning" ? "#FF9800" : "#2196F3";

  return (
    <View style={[styles.card, { backgroundColor: bgColor }]}>
      <Ionicons name={icon} size={20} color={iconColor} />
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "flex-start",
    padding: 14,
    borderRadius: 10,
    gap: 8,
  },
  message: {
    flex: 1,
    fontSize: 13,
    color: "#555",
    lineHeight: 18,
  },
});
