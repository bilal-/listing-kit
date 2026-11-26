# Install the skill

Choose the installer for the agent you use to work on the app.

| Agent | First command | Second command |
| --- | --- | --- |
| Claude Code[^install] | `/plugin marketplace add bilal-/listing-kit` | `/plugin install listing-kit@listing-kit` |
| Codex[^install] | `codex plugin marketplace add bilal-/listing-kit` | `codex plugin add listing-kit@listing-kit` |
| Copilot CLI[^install] | `copilot plugin marketplace add bilal-/listing-kit` | `copilot plugin install listing-kit@listing-kit` |
| Gemini CLI[^install] | `gemini extensions install https://github.com/bilal-/listing-kit` | |
| Universal[^install] | `npx skills add bilal-/listing-kit` | |

[^install]: not yet verified from a clean install

With a local checkout you can also give the agent [the skill file](../skills/listing-kit/SKILL.md) and access to its sibling directories.[^install] In your app directory ask it to “prepare my store listing.”

## Run the command yourself

From the kit checkout run:

```sh
skills/listing-kit/bin/listing-kit link
```

Follow the printed PATH hint. In the app directory, run `listing-kit version` and `listing-kit help`. The launcher records the kit location, so keep the checkout available. Use `listing-kit link --remove` to remove its launcher link.
