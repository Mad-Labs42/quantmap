# Pull Request Template

## Summary

Describe the change in plain English.

## Why

Why is this change needed?

## Scope

- [ ] Narrow change
- [ ] Broad change

## Risk

What could this affect?

## Validation

- [ ] Dev contract verified (`.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick` or CI equivalent)
- [ ] Tests added or updated
- [ ] Existing tests passed
- [ ] Manual validation performed
- [ ] Not validated yet

## Agent Surface

- [ ] Instruction files reviewed if behavior/tooling changed
- [ ] Workspace settings changes are intentional and minimal
- [ ] If `.agent/scripts/agent_surface_audit.py` is present in this branch, agent surface audit passed

## Notes

Anything reviewers should pay special attention to?
