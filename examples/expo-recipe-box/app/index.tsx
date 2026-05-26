import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { Link } from "expo-router";
import { recipes } from "../data/recipes";

export default function RecipesScreen() {
  return (
    <View style={styles.container} accessibilityLabel="Recipes list">
      <View style={styles.toolbar}>
        <Link href="/shopping" asChild>
          <Pressable accessibilityRole="button" accessibilityLabel="Open shopping list">
            <Text style={styles.link}>🛒 Shopping</Text>
          </Pressable>
        </Link>
        <Link href="/settings" asChild>
          <Pressable accessibilityRole="button" accessibilityLabel="Open settings">
            <Text style={styles.link}>⚙️ Settings</Text>
          </Pressable>
        </Link>
      </View>
      <FlatList
        data={recipes}
        keyExtractor={(r) => r.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <Link href={`/recipe/${item.id}`} asChild>
            <Pressable
              style={styles.card}
              accessibilityRole="button"
              accessibilityLabel={`Recipe: ${item.title}, ${item.minutes} minutes`}
            >
              <Text style={styles.emoji}>{item.emoji}</Text>
              <View style={styles.cardText}>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.meta}>{item.minutes} min</Text>
              </View>
            </Pressable>
          </Link>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  toolbar: { flexDirection: "row", justifyContent: "flex-end", gap: 16, padding: 12 },
  link: { fontSize: 15, color: "#4F46E5", fontWeight: "600" },
  list: { paddingHorizontal: 16, paddingBottom: 24 },
  card: { flexDirection: "row", alignItems: "center", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: "#eee" },
  emoji: { fontSize: 34, marginRight: 14 },
  cardText: { flex: 1 },
  title: { fontSize: 17, fontWeight: "600", color: "#111" },
  meta: { fontSize: 13, color: "#888", marginTop: 2 },
});
