class Recipe {
  final String id;
  final String title;
  final int minutes;
  final String emoji;
  final List<String> ingredients;
  final List<String> steps;

  const Recipe(this.id, this.title, this.minutes, this.emoji, this.ingredients, this.steps);
}

class Grocery {
  final String id;
  final String label;
  const Grocery(this.id, this.label);
}

const recipes = [
  Recipe("recipe_lemon_herb_pasta", "Lemon Herb Pasta", 20, "🍝",
      ["200g spaghetti", "2 lemons", "Fresh basil", "Olive oil", "Parmesan"],
      ["Boil the pasta until al dente.", "Zest and juice the lemons.", "Toss pasta with oil, lemon, and basil.", "Top with parmesan and serve."]),
  Recipe("recipe_avocado_toast", "Avocado Toast", 8, "🥑",
      ["2 slices sourdough", "1 ripe avocado", "Chili flakes", "Sea salt", "Lime"],
      ["Toast the sourdough.", "Mash avocado with lime and salt.", "Spread and sprinkle chili flakes."]),
  Recipe("recipe_berry_smoothie", "Berry Smoothie", 5, "🫐",
      ["1 cup mixed berries", "1 banana", "Greek yogurt", "Honey", "Ice"],
      ["Add everything to a blender.", "Blend until smooth.", "Pour and enjoy."]),
  Recipe("recipe_veggie_stir_fry", "Veggie Stir-Fry", 18, "🥦",
      ["Broccoli", "Bell peppers", "Soy sauce", "Garlic", "Ginger", "Rice"],
      ["Cook the rice.", "Sauté garlic and ginger.", "Add vegetables and soy sauce.", "Serve over rice."]),
  Recipe("recipe_banana_pancakes", "Banana Pancakes", 15, "🥞",
      ["2 bananas", "2 eggs", "Flour", "Maple syrup", "Butter"],
      ["Mash bananas with eggs.", "Stir in flour to a batter.", "Cook on a buttered pan.", "Serve with syrup."]),
];

const groceries = [
  Grocery("grocery_spaghetti", "Spaghetti"),
  Grocery("grocery_lemons", "Lemons"),
  Grocery("grocery_fresh_basil", "Fresh basil"),
  Grocery("grocery_avocados", "Avocados"),
  Grocery("grocery_mixed_berries", "Mixed berries"),
  Grocery("grocery_greek_yogurt", "Greek yogurt"),
];
