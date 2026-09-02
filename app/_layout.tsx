import { Stack, useRouter, useSegments } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { View, Text, ActivityIndicator, StyleSheet, TouchableOpacity } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { getDatabase } from "../src/db/database";
import { migrateDatabase } from "../src/db/migrations";
import { seedDatabase } from "../src/db/seed";
import { AuthProvider, useAuth } from "../src/features/auth/AuthContext";

function AppNavigator() {
  const { status } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const inAuthScreen = segments[0] === "auth";

  useEffect(() => {
    if (status === "loading") return;
    if (status === "unauthenticated" && !inAuthScreen) router.replace("/auth");
    if ((status === "authenticated" || status === "offline") && inAuthScreen) {
      router.replace("/(tabs)");
    }
  }, [inAuthScreen, router, status]);

  if (status === "loading") {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#4CAF50" />
      </View>
    );
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}

export default function RootLayout() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initialize = useCallback(async () => {
    setError(null);
    try {
      const db = await getDatabase();
      await migrateDatabase(db);
      await seedDatabase(db);
      setReady(true);
    } catch (e) {
      console.error("Failed to initialize app database", e);
      setReady(false);
      setError("数据库初始化失败，请重试。");
    }
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  if (!ready) {
    return (
      <View style={styles.loading}>
        {error ? (
          <>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={initialize}>
              <Text style={styles.retryText}>重试</Text>
            </TouchableOpacity>
          </>
        ) : (
          <ActivityIndicator size="large" color="#4CAF50" />
        )}
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <AuthProvider>
        <AppNavigator />
      </AuthProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#f5f5f5",
    paddingHorizontal: 24,
  },
  errorText: {
    fontSize: 15,
    color: "#666",
    textAlign: "center",
    marginBottom: 16,
  },
  retryButton: {
    backgroundColor: "#4CAF50",
    borderRadius: 10,
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  retryText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "600",
  },
});
