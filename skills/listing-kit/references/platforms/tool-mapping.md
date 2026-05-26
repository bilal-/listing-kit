# Cross-AI tool mapping

listing-kit's core logic is plain **markdown + shell**, so it runs the same under
any agent. The only thing that differs between AI platforms is the *name* of the
built-in tools the agent uses to read files, edit files, and run shell. This doc
maps them. When this skill says "read X", "write Y", or "run Z", use your
platform's equivalent below.

| Capability | Claude Code | Codex | Copilot CLI | Gemini CLI |
|---|---|---|---|---|
| Read a file | `Read` | `read_file` / shell `cat` | `read` / shell | `read_file` |
| Write/edit a file | `Write` / `Edit` | `apply_patch` | `edit` / shell | `write_file` / `replace` |
| List/search files | `Glob` / `Grep` | shell `rg`/`find` | shell | `glob` / `search_file_content` |
| Run a shell command | `Bash` | shell tool | shell | `run_shell_command` |

## Portability rules this skill follows
- **All real work is shell-outs** to `xcrun simctl`, `adb`, `flutter`, the
  Expo/RN CLI, `maestro`, and ImageMagick. Any agent that can run a shell can run
  this skill.
- **No agent-specific browser/MCP capability** is used for capture — screenshots
  come from `simctl`/`adb`.
- **Helpers that need real code** live in `scripts/` as portable POSIX shell, so
  the agent invokes them rather than relying on a platform-specific tool.

## Installing across platforms
A single canonical `SKILL.md` + `references/` + `scripts/` is the source of
truth. `scripts/package/generate-manifests.sh` emits each platform's install
manifest from it, so they never drift. See the repo README "Install" section and
`scripts/package/generate-manifests.sh`.
