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
