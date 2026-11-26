package com.example.recipebox.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val demo = intent.getStringExtra("recipeBoxState") == "demo"
        setContent { RecipeBox(demo) }
    }
}

@OptIn(ExperimentalComposeUiApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun RecipeBox(demo: Boolean) {
    var page by rememberSaveable { mutableStateOf("recipes") }
    var dark by rememberSaveable { mutableStateOf(false) }
    var checked by rememberSaveable {
        mutableStateOf(if (demo) arrayListOf("Lemons", "Avocados") else arrayListOf())
    }
    val recipe = recipes.find { it.id == page }
    val title = when (page) {
        "shopping" -> "Shopping List"
        "settings" -> "Settings"
        else -> recipe?.title ?: "Recipes"
    }
    BackHandler(enabled = page != "recipes") { page = "recipes" }

    MaterialTheme(colorScheme = if (dark) darkColorScheme() else lightColorScheme()) {
        Scaffold(
            modifier = Modifier.semantics { testTagsAsResourceId = true },
            topBar = {
                TopAppBar(title = { Text(title) }, navigationIcon = {
                    if (page != "recipes") {
                        TextButton(onClick = { page = "recipes" }, modifier = Modifier.testTag("back")) {
                            Text("Back")
                        }
                    }
                })
            },
        ) { padding ->
            key(page) {
                Column(
                    Modifier.padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    when (page) {
                        "recipes" -> Recipes(onOpen = { page = it })
                        "shopping" -> Shopping(checked) { label ->
                            checked = ArrayList(if (label in checked) checked - label else checked + label)
                        }
                        "settings" -> Settings(dark, onToggle = { dark = it })
                        else -> Detail(requireNotNull(recipe))
                    }
                }
            }
        }
    }
}

@Composable
private fun Recipes(onOpen: (String) -> Unit) {
    Row {
        TextButton(onClick = { onOpen("shopping") }, modifier = Modifier.testTag("open_shopping")) {
            Text("Shopping")
        }
        TextButton(onClick = { onOpen("settings") }, modifier = Modifier.testTag("open_settings")) {
            Text("Settings")
        }
    }
    for (entry in recipes) {
        OutlinedCard(onClick = { onOpen(entry.id) }, modifier = Modifier.fillMaxWidth().testTag(entry.id)) {
            ListItem(
                headlineContent = { Text(entry.title) },
                supportingContent = { Text("${entry.minutes} min") },
                leadingContent = { Text(entry.emoji, style = MaterialTheme.typography.headlineMedium) },
            )
        }
    }
}

@Composable
private fun Detail(recipe: Recipe) {
    Text(recipe.emoji, style = MaterialTheme.typography.displayMedium)
    Text("${recipe.minutes} min")
    Text("Ingredients", style = MaterialTheme.typography.titleLarge)
    recipe.ingredients.forEachIndexed { i, ingredient ->
        Text("• $ingredient", if (i == 0) Modifier.testTag("first_ingredient") else Modifier)
    }
    Text("Steps", style = MaterialTheme.typography.titleLarge)
    recipe.steps.forEachIndexed { i, step -> Text("${i + 1}. $step") }
}

@Composable
private fun Shopping(checked: List<String>, onToggle: (String) -> Unit) {
    for (item in groceries) {
        val selected = item.label in checked
        ListItem(
            modifier = Modifier.testTag(item.id).toggleable(
                value = selected,
                role = Role.Checkbox,
                onValueChange = { onToggle(item.label) },
            ),
            headlineContent = { Text(item.label) },
            leadingContent = { Checkbox(checked = selected, onCheckedChange = null) },
        )
    }
}

@Composable
private fun Settings(dark: Boolean, onToggle: (Boolean) -> Unit) {
    ListItem(
        modifier = Modifier.testTag("dark_theme").toggleable(
            value = dark,
            role = Role.Switch,
            onValueChange = onToggle,
        ),
        headlineContent = { Text("Dark theme") },
        trailingContent = { Switch(checked = dark, onCheckedChange = null) },
    )
    Text("Recipe Box, a listing-kit example app")
    Text("v1.0.0")
}
