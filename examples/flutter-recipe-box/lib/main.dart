import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'recipes.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const launch = MethodChannel('recipebox/launch');
  final demo = await launch.invokeMethod<bool>('demo') ?? false;
  runApp(RecipeBox(demo: demo));
}

class RecipeBox extends StatefulWidget {
  const RecipeBox({super.key, required this.demo});
  final bool demo;

  @override
  State<RecipeBox> createState() => _RecipeBoxState();
}

class _RecipeBoxState extends State<RecipeBox> {
  late final checked = <String>{if (widget.demo) ...['Lemons', 'Avocados']};
  bool dark = false;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Recipe Box',
      debugShowCheckedModeBanner: false,
      themeMode: dark ? ThemeMode.dark : ThemeMode.light,
      darkTheme: ThemeData.dark(),
      initialRoute: '/',
      onGenerateRoute: (settings) {
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (context) {
            switch (settings.name) {
              case '/shopping':
                return _page(context, 'Shopping List', StatefulBuilder(
                  builder: (context, refresh) => ListView(children: [
                    for (final item in groceries)
                      Semantics(
                        identifier: item.id,
                        child: CheckboxListTile(
                          title: Text(item.label),
                          value: checked.contains(item.label),
                          onChanged: (value) => refresh(() {
                            if (value == true) {
                              checked.add(item.label);
                            } else {
                              checked.remove(item.label);
                            }
                          }),
                        ),
                      ),
                  ]),
                ));
              case '/settings':
                return _page(context, 'Settings', ListView(children: [
                  Semantics(
                    identifier: 'dark_theme',
                    child: SwitchListTile(
                      title: const Text('Dark theme'),
                      value: Theme.of(context).brightness == Brightness.dark,
                      onChanged: (value) => setState(() => dark = value),
                    ),
                  ),
                  const ListTile(title: Text('Recipe Box, a listing-kit example app'), subtitle: Text('v1.0.0')),
                ]));
              case '/recipe':
                return _detail(context, settings.arguments! as Recipe);
              default:
                return _recipes(context);
            }
          },
        );
      },
    );
  }

  Widget _page(BuildContext context, String title, Widget body) {
    return Scaffold(
      appBar: AppBar(title: Text(title), leading: Semantics(
        identifier: 'back',
        child: BackButton(onPressed: () => Navigator.pop(context)),
      )),
      body: body,
    );
  }

  Widget _recipes(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Recipes')),
      body: ListView(children: [
        Row(mainAxisAlignment: MainAxisAlignment.end, children: [
          Semantics(identifier: 'open_shopping', child: TextButton(
            onPressed: () => Navigator.pushNamed(context, '/shopping'), child: const Text('Shopping'),
          )),
          Semantics(identifier: 'open_settings', child: TextButton(
            onPressed: () => Navigator.pushNamed(context, '/settings'), child: const Text('Settings'),
          )),
        ]),
        for (final recipe in recipes)
          Semantics(identifier: recipe.id, child: ListTile(
            leading: Text(recipe.emoji, style: Theme.of(context).textTheme.headlineMedium),
            title: Text(recipe.title),
            subtitle: Text('${recipe.minutes} min'),
            onTap: () => Navigator.pushNamed(context, '/recipe', arguments: recipe),
          )),
      ]),
    );
  }

  Widget _detail(BuildContext context, Recipe recipe) {
    final heading = Theme.of(context).textTheme.titleLarge;
    return _page(context, recipe.title, ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(recipe.emoji, style: Theme.of(context).textTheme.displayMedium),
        Text('${recipe.minutes} min'),
        const SizedBox(height: 16),
        Text('Ingredients', style: heading),
        for (var i = 0; i < recipe.ingredients.length; i++)
          Semantics(identifier: i == 0 ? 'first_ingredient' : null, child: Text('• ${recipe.ingredients[i]}')),
        const SizedBox(height: 16),
        Text('Steps', style: heading),
        for (var i = 0; i < recipe.steps.length; i++) Text('${i + 1}. ${recipe.steps[i]}'),
      ],
    ));
  }
}
