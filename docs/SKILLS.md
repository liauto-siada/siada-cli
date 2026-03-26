# Skills System Documentation

Skills are reusable instruction sets stored in `SKILL.md` files that extend Siada's AI agent capabilities. They allow you to define specialized workflows, best practices, and domain-specific knowledge that the AI can apply when working on your tasks.

## Table of Contents

- [Overview](#overview)
- [Creating a Skill](#creating-a-skill)
- [Skill File Structure](#skill-file-structure)
- [Skill Scopes](#skill-scopes)
- [Priority and Deduplication](#priority-and-deduplication)
- [Using Skills](#using-skills)
- [Best Practices](#best-practices)
- [Examples](#examples)

## Overview

The Skills system provides a way to:

- **Define reusable workflows** - Capture repetitive processes as skills
- **Share domain knowledge** - Encode team conventions and best practices
- **Extend AI capabilities** - Give the AI specialized instructions for specific tasks
- **Organize by scope** - Create project-specific, user-level, or system-wide skills

## Creating a Skill

### Step 1: Choose the Location

Skills are stored in specific directories based on their scope:

| Scope | Directory Location | Priority |
|-------|-------------------|----------|
| User | `~/.siada-cli/skills/<skill-name>/` | Highest |
| Repository | `<project>/.siada-cli/skills/<skill-name>/` | Medium |
| System | Built-in | Lowest |

### Step 2: Create the Directory Structure

```bash
# For a repository-level skill
mkdir -p .siada-cli/skills/my-skill

# For a user-level skill
mkdir -p ~/.siada-cli/skills/my-skill
```

### Step 3: Create SKILL.md

Create a `SKILL.md` file inside the skill directory:

```bash
touch .siada-cli/skills/my-skill/SKILL.md
```

## Skill File Structure

Each `SKILL.md` file must have a YAML frontmatter section followed by the skill content:

```markdown
---
name: my-skill
description: A detailed description of what this skill does and when to use it
---

# My Skill

Write specific instructions and workflows here...
```

### Required Fields

| Field | Type | Max Length | Description |
|-------|------|------------|-------------|
| `name` | string | 64 chars | Unique identifier for the skill |
| `description` | string | 1024 chars | Full description used for triggering |

### Field Guidelines

- **name**: Use lowercase with hyphens (e.g., `code-review`, `deploy-script`)
- **description**: Write a clear, detailed description that helps the AI understand when to use this skill

## Skill Scopes

Skills exist at three levels, with different priorities:

### User Level (Highest Priority)

**Location**: `~/.siada-cli/skills/`

- Personal skills across all projects
- Override repository and system skills with same name

```bash
~/.siada-cli/
└── skills/
    ├── my-personal-workflow/
    │   └── SKILL.md
    └── common-patterns/
        └── SKILL.md
```

### Repository Level (Medium Priority)

**Location**: `<project>/.siada-cli/skills/`

- Project-specific skills
- Shared with team via version control
- Override system skills with same name

```bash
my-project/
├── .siada-cli/
│   └── skills/
│       ├── build-script/
│       │   └── SKILL.md
│       └── test-workflow/
│           └── SKILL.md
```

### System Level (Lowest Priority)

Built-in skills provided by Siada. These are overridable by user or repository skills with the same name.

## Priority and Deduplication

When skills with the same name exist at multiple scopes:

1. **User skills** take precedence over all others
2. **Repository skills** take precedence over system skills
3. **System skills** are used only if no higher-priority skill exists

Example:
```
User:       deploy-app (description: "My personal deployment")
Repository: deploy-app (description: "Team deployment workflow")
System:     deploy-app (description: "Generic deployment")
→ Result: User version is used
```

## Using Skills

### Automatic Trigger

Skills are automatically triggered when:

1. **Explicit mention**: User mentions the skill name in their request
2. **Context match**: Task clearly matches a skill's description

### Manual Invocation

You can explicitly request a skill:

```
Use the code-review skill to check my changes
```

```
Apply the deploy-script skill for this deployment
```

### How Skills Work

When a skill is triggered:

1. The AI reads the `SKILL.md` file
2. Follows the instructions and workflow defined
3. Applies the skill's guidance to complete the task
4. Falls back to general approach if skill fails

## Best Practices

### Skill Design

1. **Single responsibility**: Each skill should focus on one task type
2. **Clear triggers**: Write descriptions that make it obvious when to use the skill
3. **Complete workflow**: Include all necessary steps and considerations
4. **Examples**: Provide concrete examples of usage

### Skill Folder Structure

A skill captures a capability expressed through Markdown instructions in a `SKILL.md` file. A skill folder can also include scripts, resources, and assets that the AI uses to perform a specific task.

```bash
my-skill/
├── SKILL.md           # Required: instructions + metadata
├── scripts/           # Optional: executable code
├── references/        # Optional: documentation
└── assets/            # Optional: templates, resources
```

| Component | Required | Description |
|-----------|----------|-------------|
| `SKILL.md` | ✅ Yes | Main skill definition file containing YAML frontmatter and instructions |
| `scripts/` | ❌ No | Executable scripts (shell, Python, etc.) that the AI can run |
| `references/` | ❌ No | Reference documentation, guides, or related materials |
| `assets/` | ❌ No | Templates, configuration files, or other resources |

### Naming Conventions

- Use descriptive, lowercase names
- Separate words with hyphens
- Avoid special characters
- Keep names concise but meaningful

Good: `code-review`, `api-design`, `bug-triage`
Bad: `CodeReview`, `my_skill_v2`, `do-stuff`

### Content Guidelines

- Write clear, actionable instructions
- Include context about when to use the skill
- Document any prerequisites
- Provide examples of expected input/output

## Examples

### Example 1: Code Review Skill

```markdown
---
name: code-review
description: Perform thorough code review following team standards including checking for security issues, performance concerns, and code style
---

# Code Review Skill

## Overview

This skill guides systematic code review following our team's standards.

## Checklist

1. **Security**
   - Check for SQL injection vulnerabilities
   - Verify input validation
   - Review authentication/authorization

2. **Performance**
   - Look for N+1 queries
   - Check for unnecessary computations
   - Review memory usage

3. **Code Quality**
   - Verify naming conventions
   - Check for code duplication
   - Review error handling

## Output Format

Provide feedback in this format:
- Category: [Security/Performance/Quality]
- Severity: [Critical/Warning/Info]
- Description: What the issue is
- Suggestion: How to fix it
```

### Example 2: API Design Skill

```markdown
---
name: api-design
description: Design RESTful APIs following company conventions including endpoint naming, request/response formats, and error handling patterns
---

# API Design Skill

## Principles

- Use RESTful conventions
- Consistent naming patterns
- Proper HTTP methods
- Structured error responses

## Endpoint Naming

- Use plural nouns: `/users`, `/products`
- Use kebab-case: `/user-profiles`
- Nest related resources: `/users/{id}/orders`

## Response Format

```json
{
  "data": {},
  "meta": {
    "page": 1,
    "total": 100
  }
}
```

## Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": []
  }
}
```
```

### Example 3: Deployment Skill

```markdown
---
name: deploy-production
description: Guide production deployments including pre-deployment checks, deployment steps, and post-deployment verification
---

# Production Deployment Skill

## Pre-Deployment Checklist

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Database migrations ready
- [ ] Rollback plan documented

## Deployment Steps

1. Notify team in #deployments channel
2. Create release tag
3. Run database migrations
4. Deploy application
5. Verify health checks

## Post-Deployment

1. Monitor error rates
2. Check performance metrics
3. Verify critical user flows
4. Update deployment log

## Rollback Procedure

If issues detected:
1. Revert to previous version
2. Rollback database if needed
3. Notify team of rollback
4. Create incident report
```

## Troubleshooting

### Common Issues

**Skill not being detected:**
- Verify the file is named exactly `SKILL.md`
- Check the directory structure is correct
- Ensure YAML frontmatter is valid

**Skill not triggering:**
- Make description more specific
- Use skill name explicitly in your request
- Check for higher-priority skill with same name

**Parse errors:**
- Verify YAML frontmatter starts with `---` and ends with `---`
- Check required fields (name, description) are present
- Ensure field lengths don't exceed limits

### Debugging

View loaded skills by checking the AI's system prompt section for "Available skills".

## Skill Commands

Siada provides slash commands to manage skills:

### `/skill-list`

List all available skills from all scopes (Repository, User, System).

```
/skill-list
```

Output includes:
- Skill name
- Description
- Source scope (REPO/USER/SYSTEM)

### `/skill-reload`

Reload all skills from disk. Use this command after adding, modifying, or removing skill files.

```
/skill-reload
```

This command will:
- Rescan all skill directories
- Parse and validate SKILL.md files
- Update the available skills list
- Report any parsing errors
