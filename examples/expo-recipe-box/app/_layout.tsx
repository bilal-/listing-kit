import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <>
      {/* The UI is always light, so keep status-bar icons dark (Android defaults to light). */}
      <StatusBar style="dark" />
      <Stack>
        <Stack.Screen name="index" options={{ title: "Recipes" }} />
        <Stack.Screen name="recipe/[id]" options={{ title: "Recipe" }} />
        <Stack.Screen name="shopping" options={{ title: "Shopping List" }} />
        <Stack.Screen name="settings" options={{ title: "Settings" }} />
      </Stack>
    </>
  );
}
