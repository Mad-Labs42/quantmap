# Commit Instructions

This document defines the commit and branch discipline for this repository. Read it fully before making any commit. Agents must read this before running any git command that mutates state.

## Repository split

This repo uses two branches with different purposes. Files belong to one of three categories, and the category determines what you do with them.

### Branch: `bughunt/phase-1-baseline` (or current public working branch)
- Public code and configuration
- Pushes to GitHub (`origin`)
- Users download this to run QuantMap

### Branch: `local/agent-infra`
- Private tracking documents, personal workflow files, and generated/local-only agent artifacts
- Never pushes to any remote
- Version-controlled locally for history and recovery

### File categories

**Public / repo-owned:** src/, CI workflows, pyproject.toml, sonar-project.properties, .coderabbit.yaml, .github/copilot-instructions.md, .github/instructions/, README.md, AGENTS.md, .vscode/settings.json, repo-owned `.agent` policy/instruction/script/reference/docs files, uv.lock, anything required for users or contributors to get the intended repo behavior. Repo-owned development scaffolding is not QuantMap product/runtime behavior, but it can still be versioned on the public working branch when CI, docs, or contributors rely on it. (this list may grow over time; verify with user if questions)
Goes on: `bughunt/phase-1-baseline`. Push to origin normally.

**Private but version-controlled on `local/agent-infra` only:** `.agent/artifacts/`, `.agent/handoffs/`, `.copilot/`, `docs/K.I.T.-&-ToDo/` (K.I.T., TO-DO, REPO-TODO, BUG-GATE-HIT-LIST files), and personal/local-only workflow files. These are expected to remain untracked on public branches.
Goes on: `local/agent-infra`. Never push.

**Disposable:** `scratch_mock_run.py` and any other experimental or one-off files.
Goes on: neither branch. Stays gitignored and untracked permanently.

## The three rules

**Rule 1: Never push `local/agent-infra` to any remote.**
The `local/` prefix is a convention indicating local-only. Pushing it leaks private infrastructure. Before any push, confirm the current branch with `git branch --show-current`.

**Rule 2: Run `git status` before every commit.**
Confirm the current branch and confirm only the expected files are staged. Five seconds of checking prevents most mistakes.

**Rule 3: If private generated/local-only files appear as modified or untracked on a public branch, `.gitignore` is broken.**
Private generated/local-only files should be invisible to git on public branches. If they show up, fix `.gitignore` before continuing. Do not commit them on the public branch.

## Standard commit workflows

### Public work only (src/ fixes, CI updates, public config)
git branch --show-current
Expected: bughunt/phase-1-baseline (or current public branch)
git status
Review what changed
git add <specific public files>
Do not use git add . — be explicit about what's staged
git status
Confirm only expected files are staged
git commit -m "your message"
git push origin bughunt/phase-1-baseline

### Private work only (generated artifacts, K.I.T. updates, BUG-GATE refreshes)
git checkout local/agent-infra
git branch --show-current
Confirm: local/agent-infra
git status
git add -f <specific private files>
The -f flag force-stages gitignored files
Without -f, git refuses to stage them (this is the safety mechanism)
git status
Confirm staging
git commit -m "your message"
Do NOT push. Ever.
git checkout bughunt/phase-1-baseline
Return to public branch for continued work

### Mixed work (a session that touched repo-owned and private files)

Split into two commits across two branches.
Start on the public branch
git checkout bughunt/phase-1-baseline
git branch --show-current
Commit public changes first
git add <public files only>
git status
Verify no private files are staged — they should be invisible because gitignored
git commit -m "public work description"
git push origin bughunt/phase-1-baseline
Switch to private branch
git checkout local/agent-infra
git branch --show-current
Private files are still in your working tree because they're gitignored,
not because they were tracked here. Stage them with -f.
git add -f <private files>
git status
git commit -m "private work description"
Do NOT push
Return to public branch
git checkout bughunt/phase-1-baseline

## Sanity-check commands

Run anytime you're unsure of repo state:
git branch --show-current
git status
git log --oneline -3
git log --oneline -3 local/agent-infra

First line: which branch am I on.
Second: what's pending.
Third: recent history on current branch.
Fourth: recent history on the private branch.

If anything looks wrong, stop and investigate before committing.

## First push of a new public branch

If you create a new feature branch off `main` or `bughunt/phase-1-baseline`, the first push needs `-u` to set up tracking:
git push -u origin <new-branch-name>

After that, `git push` works normally.

This does not apply to `local/agent-infra`, which never pushes.

## Pulling from GitHub
git checkout bughunt/phase-1-baseline
git pull origin bughunt/phase-1-baseline

Pulls only affect the branch you pull into. `local/agent-infra` never receives remote changes because it exists only locally.

## Gotchas to avoid

**Uncommitted changes blocking branch switch.** If `git checkout` refuses to switch because of uncommitted edits, either commit them on the current branch first or stash them with `git stash`. After switching and doing what you needed, return and `git stash pop` to restore.

**Detached HEAD state.** If you run `git checkout <commit-hash>` instead of `git checkout <branch-name>`, git puts you in detached HEAD mode. Commits made here are lost on the next branch switch. If `git status` shows "HEAD detached at..." don't commit. Switch back to a branch or create one with `git checkout -b <name>`.

**Never merge or rebase `local/agent-infra` into public branches.** The branches are meant to diverge permanently. If you need a file's content in both places, copy it manually on the target branch rather than merging.

**Never delete `local/agent-infra`.** It is the only copy of your private infrastructure's version history. If deleted, history is lost. Files on disk remain, but the branch-tracked history disappears.

**Don't use `git add .` or `git add -A`.** These can accidentally stage files you didn't intend to commit. Always list specific files.

## Restoring private/local-only files if they disappear from working tree

If switching branches or resetting causes `.agent/artifacts/`, `.agent/handoffs/`, `.copilot/`, or `docs/K.I.T.-&-ToDo/` to disappear from disk on the public branch, restore them from `local/agent-infra` without switching branches:
git branch --show-current
Confirm: bughunt/phase-1-baseline
git checkout local/agent-infra -- .agent/artifacts/ .agent/handoffs/
git checkout local/agent-infra -- .copilot/
git checkout local/agent-infra -- "docs/K.I.T.-&-ToDo/"
Unstage (they must stay working-tree-only, never staged on public branch)
git reset HEAD .agent/artifacts/ .agent/handoffs/
git reset HEAD .copilot/
git reset HEAD "docs/K.I.T.-&-ToDo/"
git status
Expected: clean working tree (files present on disk but gitignored)
Verify
.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict
Expected: PASS

## Instructions for agents running in this repository

When making commits, you must:

1. Read this file before running any git command that mutates state.
2. Classify each changed file into public, private, or disposable before staging.
3. State the classification in your pre-change echo.
4. Never use `git add .` or `git add -A`.
5. Never push `local/agent-infra`.
6. Run `git status` before and after staging and report the output.
7. Run `git branch --show-current` before switching branches.
8. Stop and ask if any file's classification is unclear.
9. Stop and ask if `git status` shows unexpected files.
10. Never merge or rebase between `local/agent-infra` and any public branch.

If a user's request would require violating any of the above, respond with "Blocked by Commit Policy" and ask for clarification before proceeding.

## Summary

Public work: commit on `bughunt/phase-1-baseline`, push to origin.
Private work: commit on `local/agent-infra`, never push.
Disposable files: stay gitignored, never commit.
`git status` is the truth. Check it before every commit.
