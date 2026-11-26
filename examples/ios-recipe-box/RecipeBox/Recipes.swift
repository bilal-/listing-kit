struct Recipe: Identifiable, Hashable {
    let id: String
    let title: String
    let minutes: Int
    let emoji: String
    let ingredients: [String]
    let steps: [String]
}

struct Grocery: Identifiable {
    let id: String
    let label: String
}

let recipes = [
    Recipe(id: "recipe_lemon_herb_pasta", title: "Lemon Herb Pasta", minutes: 20, emoji: "🍝",
           ingredients: ["200g spaghetti", "2 lemons", "Fresh basil", "Olive oil", "Parmesan"],
           steps: ["Boil the pasta until al dente.", "Zest and juice the lemons.", "Toss pasta with oil, lemon, and basil.", "Top with parmesan and serve."]),
    Recipe(id: "recipe_avocado_toast", title: "Avocado Toast", minutes: 8, emoji: "🥑",
           ingredients: ["2 slices sourdough", "1 ripe avocado", "Chili flakes", "Sea salt", "Lime"],
           steps: ["Toast the sourdough.", "Mash avocado with lime and salt.", "Spread and sprinkle chili flakes."]),
    Recipe(id: "recipe_berry_smoothie", title: "Berry Smoothie", minutes: 5, emoji: "🫐",
           ingredients: ["1 cup mixed berries", "1 banana", "Greek yogurt", "Honey", "Ice"],
           steps: ["Add everything to a blender.", "Blend until smooth.", "Pour and enjoy."]),
    Recipe(id: "recipe_veggie_stir_fry", title: "Veggie Stir-Fry", minutes: 18, emoji: "🥦",
           ingredients: ["Broccoli", "Bell peppers", "Soy sauce", "Garlic", "Ginger", "Rice"],
           steps: ["Cook the rice.", "Sauté garlic and ginger.", "Add vegetables and soy sauce.", "Serve over rice."]),
    Recipe(id: "recipe_banana_pancakes", title: "Banana Pancakes", minutes: 15, emoji: "🥞",
           ingredients: ["2 bananas", "2 eggs", "Flour", "Maple syrup", "Butter"],
           steps: ["Mash bananas with eggs.", "Stir in flour to a batter.", "Cook on a buttered pan.", "Serve with syrup."]),
]

let groceries = [
    Grocery(id: "grocery_spaghetti", label: "Spaghetti"),
    Grocery(id: "grocery_lemons", label: "Lemons"),
    Grocery(id: "grocery_fresh_basil", label: "Fresh basil"),
    Grocery(id: "grocery_avocados", label: "Avocados"),
    Grocery(id: "grocery_mixed_berries", label: "Mixed berries"),
    Grocery(id: "grocery_greek_yogurt", label: "Greek yogurt"),
]
