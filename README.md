# agent-sandbox-kit

[日本語](README.ja.md)

A kit for running AI agents (Claude Code / Codex CLI / Cursor / Antigravity) inside a
dedicated WSL2 distro (`agent-sandbox`) isolated from the Windows host.

- Creating, isolating, and provisioning the distro
- Copying projects in, connecting via Remote-SSH from an IDE (VS Code / Cursor / Antigravity), retrieving work, and removing projects
- Warning about / blocking a copied-in project that was accidentally opened on the host side (per-client hooks)
- Skills (`/sandbox-*`) for invoking all of the above from each client

See [sandbox/README.md](sandbox/README.md) for how it works and how to use it
(installed into target projects as `.sandbox-kit/README.md`).

## Requirements

- Windows 10/11 + WSL2
- Python 3.10 or later on the host (`python` command)
- Your IDE of choice with a Remote-SSH extension

## Installation

```
python install.py <project path>                                  # all clients
python install.py <project path> --clients claude,cursor          # selected clients only
python install.py <project path> --dry-run                        # show changes only
```

Re-running updates only the files that differ (idempotent). Kit-owned files that were
edited by hand are reverted to the kit version on the next run.

| Destination | Contents | Clients |
|---|---|---|
| `.sandbox-kit/` | Sandbox management scripts | all |
| `.claude/skills/sandbox-*/` | Skills | claude |
| `.agents/skills/sandbox-*/` | Skills | codex / antigravity / cursor |
| `.claude/hooks/` + `.claude/settings.json` | Accidental-open detection hook | claude |
| `.codex/hooks/` + `.codex/hooks.json` | same | codex |
| `.cursor/hooks/` + `.cursor/hooks.json` | same | cursor |
| `.agents/hooks/` + `.agents/hooks.json` | same | antigravity |

Hook registrations are merged into existing config files (only this kit's entries are
added or updated; other hooks and settings are left untouched). `.codex/hooks.json` and
`.agents/hooks.json` contain absolute paths on this machine, so add them to `.gitignore`
if the repository is shared.

First-time setup after installation:

```
python .sandbox-kit/setup_sandbox.py      # or /sandbox-setup from any client
```

## Repository layout

```
agent-sandbox-kit/
├── install.py                 installer
├── sandbox/                   → installed as .sandbox-kit/
├── hooks/
│   ├── _sandbox_guard_core.py detection logic (shared by all clients)
│   └── <client>_sandbox_guard.py  per-client adapters (stdin/stdout contract translation)
├── .claude/skills/            Skills for Claude Code
├── .agents/skills/            Skills for Codex CLI / Antigravity / Cursor
├── tools/destroy_sandbox.py   guarded destruction of the whole distro (not distributed)
└── tests/                     python -m unittest discover -s tests
```

`.claude/skills/` and `.agents/skills/` are maintained as independent sources
(even where their contents are currently identical, neither is generated from the other).

## Destroying the distro

The distro is shared by all projects, so destroy it from this repository:

```
python tools/destroy_sandbox.py                          # check git state, then destroy
python tools/destroy_sandbox.py --export-first <dest>    # back up all projects, then destroy
```

## Not yet verified on real systems

The implementation follows each client's official documentation, but the following
points have not been verified in practice:

- Codex CLI: whether hooks in `.codex/hooks.json` actually fire and `decision: block` stops the prompt
- Cursor: Windows path format of `workspace_roots`; whether hooks run twice due to compatibility loading of Claude Code hooks
- Antigravity: shell and working directory when hooks run; whether `deny` in `PreToolUse` stops all tools
- Support for `--remote ssh-remote+<host>` in the `cursor` / `antigravity-ide` commands
