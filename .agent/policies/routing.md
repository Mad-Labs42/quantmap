# routing.md

Read only the minimum policy file(s) needed.

- Repo purpose, project identity, success criteria -> `project.md`
- Module layout, ownership, dependency flow, cross-file impact -> `architecture.md`
- Scope limits, invariants, non-negotiables, trust/risk constraints -> `boundaries.md`
- Task approach, patch strategy, stop-and-ask behavior, response format -> `workflow.md`
- Validation method, proof expectations, test scope, “verified” vs “unverified” -> `testing.md`
- Tool use, search/read discipline, IDE behavior, common tool mistakes -> `tooling.md`
- Critique, audit, red-team review, assumption-challenging, anti-bloat review -> `adversarial.md`

Rules:

- Do not read all `.agent/policies/*` files by default.
- Do not read a file unless the task requires it.
- Do not read K.I.T./TO-DO tracker files unless the user asks to read or update them.
- If scope is unclear, read `routing.md`, then choose one best next file.
- If multiple files seem relevant, read the minimum set needed.
- If instructions conflict on a load-bearing issue, stop and ask.
