# Terminal Guardrails Reference

Use this file as the single source of truth for terminal guardrails, failure handling, and helper command usage.

## Scope

- Applies only in VS Code and Antigravity agent contexts.
- Use PowerShell-native syntax in PowerShell sessions.
- Do not mix Bash-specific syntax in PowerShell terminals.
- Never use Bash heredoc syntax (`<<`) in PowerShell commands.

## Pre-Mutation Safety Checks

Before any mutating command (write/move/delete):

1. Verify current directory explicitly.
2. Verify target paths explicitly.
3. Confirm the command category and expected effect before execution.
4. Run preflight guard checks for complex or multi-part commands before execution.

Preflight command:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\terminal_preflight_check.py --shell powershell --command "<command>"
```

## Failure Handling Protocol

- On first failure:
  - report concise failure cause
  - provide immediate fix attempt
- If the same command category fails more than once:
  - capture debug context before retrying
  - require a clear root-cause hypothesis before the next attempt
  - do not blind-retry

Required debug context on repeated failure:

- cwd
- full command
- exit code
- stdout tail
- stderr tail
- command resolution/path checks

## Guardrail Self-Test (Proof)

Run repeatable guardrail checks and write an artifact:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\terminal_guardrail_selftest.py
```

Artifact:

- `.agent/artifacts/terminal_guardrail_proof.json`

## Optional PowerShell Wrapper

Use when consistent output capture and immediate failure visibility is needed:

```powershell
function Invoke-AgentCommand {
  param([Parameter(Mandatory = $true)][string]$Command)
  $output = (Invoke-Expression $Command 2>&1 | Out-String)
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) { $exitCode = 0 }
  if ($exitCode -ne 0) {
    Write-Host "Command failed: $Command"
    Write-Host "Exit code: $exitCode"
    Write-Host "Output:"
    Write-Host $output
  }
  return $exitCode
}
```

Example:

```powershell
Invoke-AgentCommand ".\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict"
```
