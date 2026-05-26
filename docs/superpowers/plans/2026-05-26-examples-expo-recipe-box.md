# Examples: Expo Recipe Box (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, automation-friendly Expo/React Native example app ("Recipe Box") under `examples/`, plus its Maestro flows and docs, so listing-kit can later be run against it to produce a full committed store listing (Phase B).

**Architecture:** A minimal Expo Router (file-based routing) app with four deep-linkable, accessibility-labeled screens populated by local seed data (no backend, no auth). Maestro flows (one per screen, deep-link-first) live in `.listing-kit/flows/` and are committed as rerunnable recipes. The repo `.gitignore` is amended to track those flows while still ignoring secrets. The existing zero-dependency `tests/` suite gains a structure check for the example.

**Tech Stack:** Expo (managed) + Expo Router + TypeScript; Maestro YAML flows; existing bash test suite (bash + python3).

**Scope note:** This plan is **Phase A only** — building the app, flows, and docs. **Phase B** (running listing-kit to generate and commit the real `fastlane/` output) requires Node + Xcode/Android SDK + a simulator + Maestro and is documented in `examples/README.md` for the user to run on a tooled machine; it is **not** part of this plan.

**Prerequisites for executing this plan:** Node 18+ and network access (for `npx create-expo-app` / `npx expo install`). No simulator is required for Phase A.

**Adaptation from strict TDD:** This is an example app + docs, not a library with unit tests. "Tests" here are the appropriate verification gates: TypeScript typecheck (`npx tsc --noEmit`), JSON/YAML/structure validation, and the existing `bash tests/run.sh`. Each task still ends green and commits.

---

## File structure (created by this plan)

```
examples/
  README.md                                    # index, Phase-B procedure, "make your app ready" notes
  expo-recipe-box/
    package.json app.json tsconfig.json        # (scaffolded, then edited)
    babel.config.js .gitignore                 # (scaffolded; app-local node_modules ignore)
    app/
      _layout.tsx                              # Stack navigator (4 routes)
      index.tsx                                # Recipes list   (recipebox://)
      recipe/[id].tsx                          # Recipe detail  (recipebox://recipe/1)
      shopping.tsx                             # Shopping list  (recipebox://shopping)
      settings.tsx                             # Settings       (recipebox://settings)
    data/
      recipes.ts                               # seed recipes + shopping items
    .listing-kit/
      flows/
        recipes.yaml recipe-detail.yaml shopping.yaml settings.yaml
    fastlane/                                  # (Phase B only — NOT created here)
```

Root files modified: `.gitignore` (track example flows), `README.md` (link), `CONTRIBUTING.md` (regeneration note), `tests/structure/examples.test.sh` (new).

---

## Task 1: Scaffold the Expo app

**Files:**
- Create: `examples/expo-recipe-box/` (via scaffolding tool)
- Modify: `examples/expo-recipe-box/package.json`, `examples/expo-recipe-box/app.json`

- [ ] **Step 1: Create the app from the blank-TypeScript template**

Run from repo root:
```bash
mkdir -p examples
cd examples
npx create-expo-app@latest expo-recipe-box -t blank-typescript
cd expo-recipe-box
```
Expected: a new `expo-recipe-box/` with `App.tsx`, `app.json`, `package.json`, `tsconfig.json`, `babel.config.js`, `.gitignore`, `assets/`.

- [ ] **Step 2: Install Expo Router + navigation deps (expo picks compatible versions)**

Run (in `examples/expo-recipe-box`):
```bash
npx expo install expo-router react-native-safe-area-context react-native-screens expo-linking expo-constants react-native-gesture-handler
```
Expected: deps added to `package.json`; no version errors.

- [ ] **Step 3: Switch the entry point to expo-router and remove the template entry**

Edit `package.json` — set the `main` field:
```json
"main": "expo-router/entry",
```
Then remove the now-unused template entry component:
```bash
rm -f App.tsx
mkdir -p app data "app/recipe"
```

- [ ] **Step 4: Configure scheme + router plugin + bundle ids in `app.json`**

Edit `examples/expo-recipe-box/app.json` so the `expo` object includes these keys (keep the template's existing `name`, `icon`, `splash`, `version`, etc.; add/replace the ones below):
```json
{
  "expo": {
    "name": "Recipe Box",
    "slug": "recipe-box",
    "scheme": "recipebox",
    "orientation": "portrait",
    "userInterfaceStyle": "automatic",
    "ios": { "supportsTablet": true, "bundleIdentifier": "dev.bilalahmad.recipebox" },
    "android": { "package": "dev.bilalahmad.recipebox" },
    "plugins": ["expo-router"]
  }
}
```
(Leave `icon`, `splash`, `assetBundlePatterns` etc. from the template intact — only merge in the keys above.)

- [ ] **Step 5: Verify the project typechecks (no screens yet, so expect a "missing routes" runtime-only situation — typecheck must still pass)**

Run:
```bash
npx tsc --noEmit
```
Expected: PASS (exit 0). If `tsc` reports it cannot find `expo-router` types, ensure Step 2 completed and rerun.

- [ ] **Step 6: Commit**

Run from repo root:
```bash
git add examples/expo-recipe-box
git commit -m "feat(examples): scaffold Expo Recipe Box app (router + config)"
```

---

## Task 2: Seed data

**Files:**
- Create: `examples/expo-recipe-box/data/recipes.ts`

- [ ] **Step 1: Write the seed data module**

Create `examples/expo-recipe-box/data/recipes.ts`:
```ts
export type Recipe = {
  id: string;
  title: string;
  minutes: number;
  emoji: string;
  ingredients: string[];
  steps: string[];
};

export const recipes: Recipe[] = [
  {
    id: "1",
    title: "Lemon Herb Pasta",
    minutes: 20,
    emoji: "🍝",
    ingredients: ["200g spaghetti", "2 lemons", "Fresh basil", "Olive oil", "Parmesan"],
    steps: ["Boil the pasta until al dente.", "Zest and juice the lemons.", "Toss pasta with oil, lemon, and basil.", "Top with parmesan and serve."],
  },
  {
    id: "2",
    title: "Avocado Toast",
    minutes: 8,
    emoji: "🥑",
    ingredients: ["2 slices sourdough", "1 ripe avocado", "Chili flakes", "Sea salt", "Lime"],
    steps: ["Toast the sourdough.", "Mash avocado with lime and salt.", "Spread and sprinkle chili flakes."],
  },
  {
    id: "3",
    title: "Berry Smoothie",
    minutes: 5,
    emoji: "🫐",
    ingredients: ["1 cup mixed berries", "1 banana", "Greek yogurt", "Honey", "Ice"],
    steps: ["Add everything to a blender.", "Blend until smooth.", "Pour and enjoy."],
  },
  {
    id: "4",
    title: "Veggie Stir-Fry",
    minutes: 18,
    emoji: "🥦",
    ingredients: ["Broccoli", "Bell peppers", "Soy sauce", "Garlic", "Ginger", "Rice"],
    steps: ["Cook the rice.", "Sauté garlic and ginger.", "Add vegetables and soy sauce.", "Serve over rice."],
  },
  {
    id: "5",
    title: "Banana Pancakes",
    minutes: 15,
    emoji: "🥞",
    ingredients: ["2 bananas", "2 eggs", "Flour", "Maple syrup", "Butter"],
    steps: ["Mash bananas with eggs.", "Stir in flour to a batter.", "Cook on a buttered pan.", "Serve with syrup."],
  },
];

export type ShoppingItem = { id: string; label: string; checked: boolean };

export const shoppingList: ShoppingItem[] = [
  { id: "a", label: "Spaghetti", checked: false },
  { id: "b", label: "Lemons", checked: true },
  { id: "c", label: "Fresh basil", checked: false },
  { id: "d", label: "Avocados", checked: true },
  { id: "e", label: "Mixed berries", checked: false },
  { id: "f", label: "Greek yogurt", checked: false },
];
```

- [ ] **Step 2: Verify typecheck**

Run (in `examples/expo-recipe-box`):
```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add examples/expo-recipe-box/data/recipes.ts
git commit -m "feat(examples): add Recipe Box seed data"
```

---

## Task 3: Root layout + Recipes list screen

**Files:**
- Create: `examples/expo-recipe-box/app/_layout.tsx`
- Create: `examples/expo-recipe-box/app/index.tsx`

- [ ] **Step 1: Write the Stack navigator**

Create `examples/expo-recipe-box/app/_layout.tsx`:
```tsx
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
```

- [ ] **Step 2: Write the Recipes list screen (route `recipebox://`)**

Create `examples/expo-recipe-box/app/index.tsx`:
```tsx
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
```

- [ ] **Step 3: Verify typecheck**

Run (in `examples/expo-recipe-box`):
```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add examples/expo-recipe-box/app/_layout.tsx examples/expo-recipe-box/app/index.tsx
git commit -m "feat(examples): add layout + Recipes list screen"
```

---

## Task 4: Recipe detail screen

**Files:**
- Create: `examples/expo-recipe-box/app/recipe/[id].tsx`

- [ ] **Step 1: Write the recipe detail screen (route `recipebox://recipe/:id`)**

Create `examples/expo-recipe-box/app/recipe/[id].tsx`:
```tsx
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
```

- [ ] **Step 2: Verify typecheck**

Run (in `examples/expo-recipe-box`):
```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add examples/expo-recipe-box/app/recipe/[id].tsx
git commit -m "feat(examples): add Recipe detail screen"
```

---

## Task 5: Shopping list screen

**Files:**
- Create: `examples/expo-recipe-box/app/shopping.tsx`

- [ ] **Step 1: Write the shopping list screen (route `recipebox://shopping`)**

Create `examples/expo-recipe-box/app/shopping.tsx`:
```tsx
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
```

- [ ] **Step 2: Verify typecheck**

Run (in `examples/expo-recipe-box`):
```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add examples/expo-recipe-box/app/shopping.tsx
git commit -m "feat(examples): add Shopping list screen"
```

---

## Task 6: Settings screen

**Files:**
- Create: `examples/expo-recipe-box/app/settings.tsx`

- [ ] **Step 1: Write the settings screen (route `recipebox://settings`)**

Create `examples/expo-recipe-box/app/settings.tsx`:
```tsx
import { useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

export default function SettingsScreen() {
  const [dark, setDark] = useState(false);

  return (
    <View style={styles.container} accessibilityLabel="Settings">
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
```

- [ ] **Step 2: Verify typecheck**

Run (in `examples/expo-recipe-box`):
```bash
npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add examples/expo-recipe-box/app/settings.tsx
git commit -m "feat(examples): add Settings screen"
```

---

## Task 7: Maestro flows

**Files:**
- Create: `examples/expo-recipe-box/.listing-kit/flows/recipes.yaml`
- Create: `examples/expo-recipe-box/.listing-kit/flows/recipe-detail.yaml`
- Create: `examples/expo-recipe-box/.listing-kit/flows/shopping.yaml`
- Create: `examples/expo-recipe-box/.listing-kit/flows/settings.yaml`

- [ ] **Step 1: Write the four flows (deep-link first, with a label assertion)**

Create `examples/expo-recipe-box/.listing-kit/flows/recipes.yaml`:
```yaml
appId: dev.bilalahmad.recipebox
---
- launchApp:
    clearState: true
- openLink: recipebox://
- assertVisible:
    id: "Recipes list"
```

Create `examples/expo-recipe-box/.listing-kit/flows/recipe-detail.yaml`:
```yaml
appId: dev.bilalahmad.recipebox
---
- openLink: recipebox://recipe/1
- assertVisible: "Ingredients"
```

Create `examples/expo-recipe-box/.listing-kit/flows/shopping.yaml`:
```yaml
appId: dev.bilalahmad.recipebox
---
- openLink: recipebox://shopping
- assertVisible:
    id: "Shopping list"
```

Create `examples/expo-recipe-box/.listing-kit/flows/settings.yaml`:
```yaml
appId: dev.bilalahmad.recipebox
---
- openLink: recipebox://settings
- assertVisible:
    id: "Settings"
```

- [ ] **Step 2: Sanity-check each flow declares an app id and an action**

Run from repo root:
```bash
for f in examples/expo-recipe-box/.listing-kit/flows/*.yaml; do
  grep -q '^appId:' "$f" && grep -q 'openLink:' "$f" && echo "ok: $f" || echo "BAD: $f"
done
```
Expected: `ok:` for all four files.

- [ ] **Step 3: Commit** (these will not be tracked yet — the `.gitignore` negation in Task 8 fixes that; commit anyway so the working tree is captured once ignore is updated)

Defer the commit to Task 8 (the files are ignored until then). Proceed to Task 8.

---

## Task 8: Track the committed flows in `.gitignore`

**Files:**
- Modify: `.gitignore` (repo root)

- [ ] **Step 1: Confirm the flows are currently ignored**

Run from repo root:
```bash
git check-ignore examples/expo-recipe-box/.listing-kit/flows/recipes.yaml && echo "ignored (expected before fix)"
```
Expected: prints the path + "ignored (expected before fix)" (exit 0 = matched an ignore rule).

- [ ] **Step 2: Add the negation rules to `.gitignore`**

In the repo-root `.gitignore`, replace the line:
```
.listing-kit/
```
with:
```
# listing-kit local state — NEVER commit secrets (see skill §9.1 secrets boundary)
.listing-kit/
# ...but DO track the Maestro flows shipped with example apps (recipes, not secrets)
!examples/expo-recipe-box/.listing-kit/
!examples/expo-recipe-box/.listing-kit/flows/
!examples/expo-recipe-box/.listing-kit/flows/**
```
(The existing comment line above `.listing-kit/` can be left as-is or merged; the key is the three `!` negations directly after the `.listing-kit/` rule.)

- [ ] **Step 3: Verify the flows are now tracked but secrets would still be ignored**

Run from repo root:
```bash
git check-ignore examples/expo-recipe-box/.listing-kit/flows/recipes.yaml; echo "exit=$? (expect 1 = NOT ignored)"
git check-ignore examples/expo-recipe-box/.listing-kit/secrets.local; echo "exit=$? (expect 0 = still ignored)"
```
Expected: first command exit `1` (flows tracked); second exit `0` (a hypothetical secret still ignored — caught by `*.local` / `secrets.local`).

- [ ] **Step 4: Commit the flows + the .gitignore change together**

```bash
git add .gitignore examples/expo-recipe-box/.listing-kit/flows
git commit -m "feat(examples): add Maestro flows + track them via .gitignore negation"
```

---

## Task 9: Documentation

**Files:**
- Create: `examples/README.md`
- Modify: `README.md` (repo root) — add a "See it in action" link
- Modify: `CONTRIBUTING.md` — note example regeneration cadence

- [ ] **Step 1: Write `examples/README.md`**

Create `examples/README.md`:
```markdown
# Examples

Real apps you can run listing-kit against — to see what it produces, and to test
changes against. Each example is a deliberately minimal but **automation-friendly**
app: it has a URL scheme, accessibility labels on every interactive element, and a
demo-data mode (populated screens, no login wall).

| Example | Stack | Status |
|---|---|---|
| [`expo-recipe-box`](expo-recipe-box) | Expo / React Native | app ✅ · generated listing ⏳ (Phase B) |
| _native iOS (SwiftUI)_ | — | planned |
| _native Android (Compose)_ | — | planned |
| _Flutter_ | — | planned |

## expo-recipe-box

A tiny recipe saver with four deep-linkable screens:

| Screen | Deep link |
|---|---|
| Recipes (list) | `recipebox://` |
| Recipe detail | `recipebox://recipe/1` |
| Shopping list | `recipebox://shopping` |
| Settings | `recipebox://settings` |

### Run the app
```sh
cd examples/expo-recipe-box
npm install
npx expo start            # press i (iOS sim) or a (Android emulator)
```

### Generate the store listing (Phase B)
This is what produces the committed `expo-recipe-box/fastlane/` output, and is the
first real end-to-end run of the skill. Requires Node, Xcode and/or Android SDK, a
booted simulator/emulator, and Maestro.

1. Boot a simulator/emulator and run the app (above).
2. From an agent with the listing-kit skill, point it at this folder:
   > "Use listing-kit to generate App Store and Google Play assets for examples/expo-recipe-box."
3. The skill detects Expo, reuses the committed `.listing-kit/flows/`, captures
   screenshots, writes the `fastlane/` tree, and runs the secret scan.
4. Commit the generated `fastlane/` tree.

### What makes it "listing-kit-ready"
The three things the skill relies on, all visible in the source:
- **URL scheme** — `expo.scheme: "recipebox"` in `app.json`; routes under `app/`.
- **Accessibility labels** — every screen and control has an `accessibilityLabel`.
- **Demo data** — `data/recipes.ts` seeds populated screens; no auth, no network.
```

- [ ] **Step 2: Add a "See it in action" link to the main README**

In repo-root `README.md`, immediately after the `## How it works` section's final paragraph (the line ending `…not editing the core.`), add a new section:
```markdown
## See it in action

[`examples/expo-recipe-box`](examples/expo-recipe-box) is a complete, automation-friendly
Expo app you can run listing-kit against. See [`examples/`](examples/) for the full set
(native iOS, Android, and Flutter examples are planned).
```

- [ ] **Step 3: Add a regeneration note to CONTRIBUTING**

In `CONTRIBUTING.md`, under the `### Generated files` subsection, append this paragraph:
```markdown
**Example output** under `examples/*/fastlane/` is generated by running listing-kit
against the example apps (Phase B) and is regenerated **periodically, not per-PR** —
it needs simulators and may lag the latest store sizes. Don't block a PR on it.
```

- [ ] **Step 4: Verify markdown links resolve (uses the existing structure test machinery)**

Run from repo root:
```bash
bash tests/run.sh 2>&1 | tail -3
```
Expected: `ALL PASS` (the existing link check covers `README.md` and `CONTRIBUTING.md`; the new `examples/` and `examples/expo-recipe-box` link targets are real directories).

- [ ] **Step 5: Commit**

```bash
git add examples/README.md README.md CONTRIBUTING.md
git commit -m "docs(examples): add examples README, main-README link, contributing note"
```

---

## Task 10: Structure test for the example

**Files:**
- Create: `tests/structure/examples.test.sh`
- Modify: `tests/structure/repo-consistency.test.sh` (add `examples/README.md` to the link check loop)

- [ ] **Step 1: Write the examples structure test**

Create `tests/structure/examples.test.sh`:
```bash
#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/../helpers.sh"

APP="$ROOT/examples/expo-recipe-box"

it "example app.json is valid JSON and registers the recipebox scheme"
assert_file "$APP/app.json"
if json_valid "$APP/app.json"; then pass "valid JSON"; else fail "invalid app.json"; fi
assert_eq "recipebox" "$(json_path "$APP/app.json" "['expo']['scheme']")" "expo.scheme"

it "expo-router is the entry point and a plugin"
assert_eq "expo-router/entry" "$(json_get "$APP/package.json" main)" "package.json main"

it "all four screens exist"
for f in index.tsx "recipe/[id].tsx" shopping.tsx settings.tsx; do
  assert_file "$APP/app/$f"
done

it "each Maestro flow declares an appId and an action"
flows=0
for f in "$APP/.listing-kit/flows/"*.yaml; do
  flows=$((flows + 1))
  if grep -q '^appId:' "$f" && grep -q 'openLink:' "$f"; then pass "${f##*/}"; else fail "malformed flow: $f"; fi
done
it "found the expected four flows"
assert_eq 4 "$flows"

summary
```

- [ ] **Step 2: Add `examples/README.md` to the existing link check**

In `tests/structure/repo-consistency.test.sh`, change the link-check loop line:
```bash
for md in README.md docs/GUIDE.md CONTRIBUTING.md; do
```
to:
```bash
for md in README.md docs/GUIDE.md CONTRIBUTING.md examples/README.md; do
```

- [ ] **Step 3: Run the full suite**

Run from repo root:
```bash
bash tests/run.sh 2>&1 | tail -5
```
Expected: `ALL PASS`, with the new `structure/examples.test.sh` reporting its assertions (valid app.json, scheme, entry point, four screens, four flows).

- [ ] **Step 4: Commit**

```bash
git add tests/structure/examples.test.sh tests/structure/repo-consistency.test.sh
git commit -m "test(examples): structure checks for Recipe Box app + flows"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** §3 app/screens → Tasks 3–6; §3.1 scheme/labels/demo-data → Tasks 1,2,3–6; §4 folder structure → Tasks 1,7,8; §6 Phase A items (app, flows, README, gitignore negation, main-README link) → Tasks 1–9; §7 optional structure test → Task 10; §8 docs → Task 9. Phase B (§5/§6) intentionally documented only (Task 9 Step 1), not implemented. ✅
- **Placeholders:** none — all code and commands are complete.
- **Type/name consistency:** `Recipe`, `ShoppingItem`, `recipes`, `shoppingList` defined in Task 2 and used unchanged in Tasks 3–6; route names in `_layout.tsx` (`index`, `recipe/[id]`, `shopping`, `settings`) match the created files and the deep links in the flows; `appId` `dev.bilalahmad.recipebox` matches `app.json` `ios.bundleIdentifier` / `android.package`. ✅
- **Known external risk:** exact Expo/RN package versions come from `create-expo-app` + `expo install` at run time (not hard-pinned here) precisely so they stay mutually compatible; the only version-sensitive assertion is `tsc --noEmit`, which the executor runs after each task.
