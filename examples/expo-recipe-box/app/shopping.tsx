import { useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { shoppingList as seed, ShoppingItem } from "../data/recipes";

export default function ShoppingScreen() {
  const [items, setItems] = useState<ShoppingItem[]>(seed);

  const toggle = (id: string) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, checked: !it.checked } : it)));

  return (
    <View style={styles.container} accessibilityLabel="Shopping list">
      <FlatList
        data={items}
        keyExtractor={(i) => i.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => toggle(item.id)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: item.checked }}
            accessibilityLabel={`${item.label}, ${item.checked ? "checked" : "unchecked"}`}
          >
            <Text style={styles.box}>{item.checked ? "☑️" : "⬜️"}</Text>
            <Text style={[styles.label, item.checked && styles.done]}>{item.label}</Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  list: { padding: 16 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12 },
  box: { fontSize: 22, marginRight: 12 },
  label: { fontSize: 16, color: "#111" },
  done: { color: "#aaa", textDecorationLine: "line-through" },
});
