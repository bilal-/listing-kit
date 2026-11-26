import SwiftUI

@main
struct RecipeBoxApp: App {
    var body: some Scene {
        WindowGroup {
            RecipesView()
        }
    }
}

private enum Page: Hashable {
    case recipe(Recipe), shopping, settings
}

private struct RecipesView: View {
    @State private var path: [Page] = []
    @State private var checked: Set<String> = UserDefaults.standard.string(forKey: "recipeBoxState") == "demo"
        ? ["Lemons", "Avocados"] : []
    @State private var dark = false

    var body: some View {
        NavigationStack(path: $path) {
            List(recipes) { recipe in
                Button {
                    path.append(.recipe(recipe))
                } label: {
                    HStack(spacing: 14) {
                        Text(recipe.emoji).font(.largeTitle)
                        VStack(alignment: .leading) {
                            Text(recipe.title).font(.headline)
                            Text("\(recipe.minutes) min").foregroundStyle(.secondary)
                        }
                    }.padding(.vertical, 5)
                }
                .accessibilityIdentifier(recipe.id)
            }
            .navigationTitle("Recipes")
            .toolbar {
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    Button("Shopping") { path.append(.shopping) }
                        .accessibilityIdentifier("open_shopping")
                    Button("Settings") { path.append(.settings) }
                        .accessibilityIdentifier("open_settings")
                }
            }
            .navigationDestination(for: Page.self) { page in
                destination(page)
                    .navigationBarBackButtonHidden(true)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarLeading) {
                            Button("Back") { path.removeLast() }
                                .accessibilityIdentifier("back")
                        }
                    }
            }
        }
        .preferredColorScheme(dark ? .dark : .light)
    }

    @ViewBuilder private func destination(_ page: Page) -> some View {
        switch page {
        case .recipe(let recipe):
            List {
                VStack(alignment: .leading) {
                    Text(recipe.emoji).font(.largeTitle)
                    Text("\(recipe.minutes) min")
                }
                Section("Ingredients") {
                    ForEach(recipe.ingredients.indices, id: \.self) { i in
                        Text(recipe.ingredients[i])
                            .accessibilityIdentifier(i == 0 ? "first_ingredient" : "ingredient_\(i + 1)")
                    }
                }
                Section("Steps") {
                    ForEach(recipe.steps.indices, id: \.self) { i in
                        Text("\(i + 1). \(recipe.steps[i])")
                    }
                }
            }.navigationTitle(recipe.title)
        case .shopping:
            List(groceries) { item in
                Button {
                    if checked.contains(item.label) {
                        checked.remove(item.label)
                    } else {
                        checked.insert(item.label)
                    }
                } label: {
                    Label(item.label, systemImage: checked.contains(item.label) ? "checkmark.square.fill" : "square")
                        .strikethrough(checked.contains(item.label))
                }
                .accessibilityValue(checked.contains(item.label) ? "Checked" : "Unchecked")
                .accessibilityIdentifier(item.id)
            }.navigationTitle("Shopping List")
        case .settings:
            Form {
                Toggle("Dark theme", isOn: $dark).accessibilityIdentifier("dark_theme")
                Section {
                    Text("Recipe Box, a listing-kit example app")
                    Text("v1.0.0").foregroundStyle(.secondary)
                }
            }.navigationTitle("Settings")
        }
    }
}
