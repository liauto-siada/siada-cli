# Wiki Documentation Summary

Generated: 2026-09-24 14:10:03
Repository: siada-agenthub
Commit: `0e67ede2d0170b8819086cd02778373b10bfa249`

## Generation Status

**Overall Status**: ✅ Complete

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Pages | 2 | 2 | ✅ |
| Sections | 13 | 13 | ✅ |
| Citations | - | 108 | ✅ |
| Diagrams | 5 | 5 valid | ✅ |

## Page Details

| Page | Title | Sections | Citations | Diagrams | Status |
|------|-------|----------|-----------|----------|--------|
| 01_user-agent-definition.md | 用户自定义 Agent 定义 | 4/4 | 51 | 2 | ✅ |
| 02_user-agent-call-graph.md | 用户自定义 Agent 调用链路 | 9/9 | 57 | 3 | ✅ |

## Source Coverage

### Covered Files

- `siada/agent_hub/coder/prompt/base/prompt_builder.py` - cited in 01_user-agent-definition.md
- `siada/agent_hub/coder/prompt/code_gen_prompt.py` - cited in 01_user-agent-definition.md
- `siada/agent_hub/coder/sub_task_agent.py` - cited in 02_user-agent-call-graph.md
- `siada/services/agents/__init__.py` - cited in 01_user-agent-definition.md
- `siada/services/agents/config.py` - cited in 01_user-agent-definition.md
- `siada/services/agents/loader.py` - cited in 01_user-agent-definition.md
- `siada/services/agents/models.py` - cited in 01_user-agent-definition.md
- `siada/services/agents/renderer.py` - cited in 01_user-agent-definition.md
- `siada/services/agents/runtime.py` - cited in 02_user-agent-call-graph.md
- `siada/services/sub_agent_run_config.py` - cited in 02_user-agent-call-graph.md
- `siada/tools/agent/run_subtask.py` - cited in 02_user-agent-call-graph.md

## Issues

### Errors

None

### Recommendations

- None - documentation looks good!

## Validation Notes

- **Structure**: `validate_docs_structure.py` — 2 pages / 13 sections, `is_valid: true`, 0 errors, 0 warnings.
- **Mermaid**: `mmdc` (mermaid-cli) is not installed in this environment, so `validate_mermaid.py`
  reported every block as `cli_unavailable`. Diagrams were validated instead with the `mermaid`
  parser (`mermaid.parse()`, mermaid 11 + jsdom) — 5/5 blocks parsed successfully:
  - `01_user-agent-definition.md`: 2 flowcharts
  - `02_user-agent-call-graph.md`: 2 flowcharts + 1 sequence diagram
- **Citations**: 108 citations checked against the working tree (file existence, range bounds,
  display/URL consistency) — 0 problems.
