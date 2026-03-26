---
name: skill-creator
description: Help users create new skills by generating SKILL.md files with proper frontmatter, instructions, and directory structure. Use when asked to create, make, or set up a new skill.
metadata:
  short-description: Create new skill files
---

# Skill Creator

This skill helps you create new skills for siada-agenthub.

## Workflow

1. Ask the user for:
   - Skill name (use kebab-case, e.g., `my-new-skill`)
   - Brief description (what the skill does)
   - Detailed instructions (how to use the skill)

2. Create the skill directory structure:
   ```
   <target>/.siada/skills/<skill-name>/
   ├── SKILL.md
   ├── scripts/      (optional)
   └── references/   (optional)
   ```

3. Generate the SKILL.md file with:
   - YAML frontmatter (name, description)
   - Markdown body with instructions

## Template

Use this template when creating new skills:

```markdown
---
name: <skill-name>
description: <brief-description-explaining-when-to-use-this-skill>
metadata:
  short-description: <even-shorter-description>
---

# <Skill Title>

<Detailed instructions for using this skill>

## Workflow

1. Step one
2. Step two
3. Step three

## Notes

- Important consideration 1
- Important consideration 2
```

## Placement Guidelines

- **Repository-specific skills**: Place in `<project>/.siada/skills/`
  - Best for project-specific workflows
  - Shared with the team via version control

- **User-wide skills**: Place in `~/.siada-cli/skills/`
  - Best for personal productivity skills
  - Available across all projects

## Best Practices

1. **Clear naming**: Use descriptive kebab-case names (e.g., `code-review`, `deploy-staging`)
2. **Focused scope**: Each skill should do one thing well
3. **Good description**: The description is crucial for model triggering - make it specific
4. **Step-by-step workflow**: Break down the process into clear steps
5. **Include examples**: Add examples when helpful for clarity
