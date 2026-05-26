import { ScrollView, StyleSheet, Text } from "react-native";
import { Stack, useLocalSearchParams } from "expo-router";
import { recipes } from "../../data/recipes";

export default function RecipeDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const recipe = recipes.find((r) => r.id === id) ?? recipes[0];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      accessibilityLabel={`Recipe detail: ${recipe.title}`}
    >
      <Stack.Screen options={{ title: recipe.title }} />
      <Text style={styles.hero}>{recipe.emoji}</Text>
      <Text style={styles.title}>{recipe.title}</Text>
      <Text style={styles.meta}>{recipe.minutes} min</Text>

      <Text style={styles.section}>Ingredients</Text>
      {recipe.ingredients.map((ing, i) => (
        <Text key={`ing-${i}`} style={styles.item} accessibilityLabel={`Ingredient: ${ing}`}>
          • {ing}
        </Text>
      ))}

      <Text style={styles.section}>Steps</Text>
      {recipe.steps.map((s, i) => (
        <Text key={`step-${i}`} style={styles.item} accessibilityLabel={`Step ${i + 1}: ${s}`}>
          {i + 1}. {s}
        </Text>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  content: { padding: 20 },
  hero: { fontSize: 64, textAlign: "center" },
  title: { fontSize: 24, fontWeight: "700", textAlign: "center", color: "#111" },
  meta: { fontSize: 14, color: "#888", textAlign: "center", marginBottom: 16 },
  section: { fontSize: 18, fontWeight: "700", color: "#4F46E5", marginTop: 18, marginBottom: 6 },
  item: { fontSize: 15, color: "#222", lineHeight: 24 },
});
