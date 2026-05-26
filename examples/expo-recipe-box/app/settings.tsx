import { useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

export default function SettingsScreen() {
  const [dark, setDark] = useState(false);

  return (
    <View style={styles.container} accessibilityLabel="Settings" testID="Settings">
      <View style={styles.row}>
        <Text style={styles.label}>Dark theme</Text>
        <Switch value={dark} onValueChange={setDark} accessibilityLabel="Toggle dark theme" />
      </View>
      <View style={styles.divider} />
      <Text style={styles.about}>Recipe Box — a listing-kit example app</Text>
      <Text style={styles.version}>v1.0.0</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", padding: 20 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 12 },
  label: { fontSize: 16, color: "#111" },
  divider: { height: 1, backgroundColor: "#eee", marginVertical: 12 },
  about: { fontSize: 14, color: "#444" },
  version: { fontSize: 13, color: "#999", marginTop: 4 },
});
