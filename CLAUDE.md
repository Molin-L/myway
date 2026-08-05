# myway — Claude Code plugin marketplace

This is a **plugin repo**, not a product repo: it ships skills/templates, has
no build, no tests, and no release pipeline.

The skills are dual-agent: Claude Code loads them via the plugin manifest,
OpenAI Codex via the `.agents/skills/` symlinks (both read the same SKILL.md
open standard). Content lives in ONE place — `plugins/myway/skills/` — and
everything else is a symlink; never duplicate skill content.

## Workflow

- **Commit directly to `main`.** Do NOT apply the `implement-change` /
  release-flow workflow here (no issues, no pre-release trains, no change
  requests) — that workflow is what this repo *ships*, not how it develops.
- Use conventional commits (`feat(my-ci): …`, `docs: …`).

## Layout

- `plugins/myway/` — the plugin; register new skills in
  `.claude-plugin/plugin.json` (`skills` array).
- `plugins/myway/skills/<name>/` — one skill each: `SKILL.md` +
  `references/` + optional `templates/` and `scripts/` (scripts committed
  executable).
- `.agents/skills/<name>` — relative symlink to the skill dir, so Codex
  discovers skills when working inside this repo. **Adding a skill means
  both registrations**: the `plugin.json` entry AND
  `ln -s ../../plugins/myway/skills/<name> .agents/skills/<name>`.
- `AGENTS.md` — symlink to `CLAUDE.md` (Codex reads AGENTS.md).
- `docs/adr/` — decisions that shape the skills (e.g. ADR 0001: the
  pre-release branch name is the version source of truth).

## Verification

For skills carrying code: `bash -n` every script, and parse every YAML
template (GitLab templates need the `!reference` tag registered).
