# Install the skill

Choose the installer for the agent you use to work on the app.

| Agent (clean installs unverified) | First command | Second command |
| --- | --- | --- |
| Claude Code | `/plugin marketplace add bilal-/listing-kit` | `/plugin install listing-kit@listing-kit` |
| Codex | `codex plugin marketplace add bilal-/listing-kit` | `codex plugin add listing-kit@listing-kit` |
| Copilot CLI | `copilot plugin marketplace add bilal-/listing-kit` | `copilot plugin install listing-kit@listing-kit` |
| Gemini CLI | `gemini extensions install https://github.com/bilal-/listing-kit` | |
| Universal | `npx skills add bilal-/listing-kit` | |

The local checkout setup is also unverified. To use it, give the agent [the skill file](../skills/listing-kit/SKILL.md) and access to its sibling directories. In your app directory ask it to “prepare my store listing.”

## Run the command yourself

The plugin does not add the launcher to PATH. Ask the agent to run `bin/listing-kit link` from the installed skill directory. From a kit checkout, run the bundled launcher.

```sh
skills/listing-kit/bin/listing-kit link
```

Follow the printed PATH hint. In the app directory, run `listing-kit version` and `listing-kit help`. The launcher records the kit location, so keep the checkout available. Use `listing-kit link --remove` to remove its launcher link.
