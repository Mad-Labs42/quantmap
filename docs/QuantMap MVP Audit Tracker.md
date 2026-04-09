QuantMap MVP Audit Tracker — Updated
✅ Closed (Implemented, needs spot-check)

These now have direct evidence of implementation in the attached remediation docs.

Fatal config visibility / silent erasure
analyze.py now includes all attempted configs and creates dummy stats for failed/OOM/no-request configs.
TTFT normalization distortion
1000/x inversion replaced with linear -1 * latency.
Low-sample CV honesty
Low-N CV display now renders N/A (N<3) rather than misleading 0.0%.
OOM boundary blindspot
Mid-cycle log-tail parsing added to catch runtime OOMs, not just startup allocation failures.
Thermal resume console leakage
Historical thermal totals now reloaded from SQLite on resume.
Elimination reason propagation for fatal configs
Fatal/dummy stats configs now get explicit elimination reasons into diagnostics.
Minimum valid warm sample floor
Global floor lowered to 3. This aligns with the later MVP policy better than the earlier 10, though full Option C consistency still needs auditing.
🟡 Closed (Claimed verified, but only via limited verification)

These were said to be checked through python rescore.py --all, which is useful but not enough to fully close them.

Rescore-path integrity
Antigravity says historic campaigns executed cleanly through updated aggregation, filtering, scoring, and reporting paths. That is a real signal, but it is narrower than a full runtime validation.
⚠️ Still open / not fully proven

These remain real next-step items.

raw.jsonl vs SQLite source-of-truth enforcement
The plan explicitly left this as an open question: rewrite/truncate raw.jsonl, or warn users and treat DB as canonical. I do not see a documented closure here.
Option C validity consistency everywhere
Lowering min_valid_warm_count to 3 is not the same thing as proving the full hybrid policy is enforced consistently across analysis, scoring, filtering, and reporting. This still needs code-path verification.
Summary vs detail consistency
I do not see evidence in these docs that summaries were systematically audited to ensure they never outrun warnings or contradictions in detailed sections.
End-to-end truthfulness under stress
rescore.py --all validates historical data paths, but it does not prove correctness for:
all configs fail
only one config passes
partial telemetry
mixed success rates
live crash recovery paths
Hidden fallback regressions
We know one fallback bug was fixed earlier, but these documents do not show a systematic sweep for other or 0, .get(default), or silent coercion patterns.