import { Stack } from "expo-router";

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: "Recipes" }} />
      <Stack.Screen name="recipe/[id]" options={{ title: "Recipe" }} />
      <Stack.Screen name="shopping" options={{ title: "Shopping List" }} />
      <Stack.Screen name="settings" options={{ title: "Settings" }} />
    </Stack>
  );
}
