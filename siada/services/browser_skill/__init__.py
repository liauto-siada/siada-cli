"""Browser Skill Graph: agent-executed browser tasks with human mid-flight
interventions, distilled into an evidence-backed, incrementally maintained
Playbook.

See design_docs/browser-skill-graph-design.md for the full design.

Modules:
- models       : ReplayStep / VerificationResult / ExecutionRecord / RegistryEntry
- paths        : filesystem locations under ~/.siada-cli/workspace/
- event_utils  : event helpers (domain parsing, sanitization, replay steps)
- verification : MCP result parsing, page observation, fixed postconditions
- playbook     : SQLite truth source (queue, leases, entries, deltas, audit)
- distiller    : Reflector -> Curator -> transactional delta (LLM)
- registry     : skill index + verified-execution skill publishing
- matcher      : per-session real-time mid-segment prediction state machine
- executor     : permission-gated replay/autonomous execution with verification
- pipeline     : managed background worker + daemon drain entry point
"""
