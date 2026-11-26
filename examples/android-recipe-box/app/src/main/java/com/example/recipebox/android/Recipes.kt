package com.example.recipebox.android

internal data class Recipe(
    val id: String,
    val title: String,
    val minutes: Int,
    val emoji: String,
    val ingredients: List<String>,
    val steps: List<String>,
)

internal data class Grocery(val id: String, val label: String)

internal val recipes = listOf(
    Recipe("recipe_lemon_herb_pasta", "Lemon Herb Pasta", 20, "🍝",
        listOf("200g spaghetti", "2 lemons", "Fresh basil", "Olive oil", "Parmesan"),
        listOf("Boil the pasta until al dente.", "Zest and juice the lemons.", "Toss pasta with oil, lemon, and basil.", "Top with parmesan and serve.")),
    Recipe("recipe_avocado_toast", "Avocado Toast", 8, "🥑",
        listOf("2 slices sourdough", "1 ripe avocado", "Chili flakes", "Sea salt", "Lime"),
        listOf("Toast the sourdough.", "Mash avocado with lime and salt.", "Spread and sprinkle chili flakes.")),
    Recipe("recipe_berry_smoothie", "Berry Smoothie", 5, "🫐",
        listOf("1 cup mixed berries", "1 banana", "Greek yogurt", "Honey", "Ice"),
        listOf("Add everything to a blender.", "Blend until smooth.", "Pour and enjoy.")),
    Recipe("recipe_veggie_stir_fry", "Veggie Stir-Fry", 18, "🥦",
        listOf("Broccoli", "Bell peppers", "Soy sauce", "Garlic", "Ginger", "Rice"),
        listOf("Cook the rice.", "Sauté garlic and ginger.", "Add vegetables and soy sauce.", "Serve over rice.")),
    Recipe("recipe_banana_pancakes", "Banana Pancakes", 15, "🥞",
        listOf("2 bananas", "2 eggs", "Flour", "Maple syrup", "Butter"),
        listOf("Mash bananas with eggs.", "Stir in flour to a batter.", "Cook on a buttered pan.", "Serve with syrup.")),
)

internal val groceries = listOf(
    Grocery("grocery_spaghetti", "Spaghetti"),
    Grocery("grocery_lemons", "Lemons"),
    Grocery("grocery_fresh_basil", "Fresh basil"),
    Grocery("grocery_avocados", "Avocados"),
    Grocery("grocery_mixed_berries", "Mixed berries"),
    Grocery("grocery_greek_yogurt", "Greek yogurt"),
)
