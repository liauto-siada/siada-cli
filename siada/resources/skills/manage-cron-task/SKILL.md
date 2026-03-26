---
name: manage-cron-task
description: Manage crontab scheduled tasks (create, update, delete, list). Use when the user wants to add, modify, remove, or view periodic scheduled tasks that run automatically via ProactiveAgent.
metadata:
  short-description: Manage crontab scheduled tasks
---

# Manage Cron Task

Manage user-defined crontab scheduled tasks stored in `~/.siada-cli/workspace/cron_tasks.json`.
Each task runs on a cron schedule and its `instruction` is executed by CodeGenAgent when triggered.

## Script

```bash
python {skill_dir}/scripts/manage_cron_task.py --action <action> [options]
```

Replace `{skill_dir}` with the absolute path to this skill directory.

## Actions

### list — List all tasks

```bash
python scripts/manage_cron_task.py --action list
python scripts/manage_cron_task.py --action list --enabled-only
python scripts/manage_cron_task.py --action list --sort-by name
```

Options: `--enabled-only`, `--sort-by [name|created_at|next_run]` (default: `next_run`)

### create — Create a new task

```bash
python scripts/manage_cron_task.py --action create \
  --name "Daily Report" \
  --cron-expr "0 9 * * 1-5" \
  --instruction "Generate a daily summary of yesterday's work and save to memory"
```

Required: `--name`, `--cron-expr`, `--instruction`  
Optional: `--enabled [true|false]` (default: true)

### update — Update an existing task

```bash
# Update schedule
python scripts/manage_cron_task.py --action update --task-id "abc-123" --cron-expr "0 18 * * *"

# Disable task
python scripts/manage_cron_task.py --action update --task-id "abc-123" --enabled false

# Update instruction
python scripts/manage_cron_task.py --action update --task-id "abc-123" \
  --instruction "New instruction text"
```

Required: `--task-id`  
At least one of: `--name`, `--cron-expr`, `--instruction`, `--enabled`

### delete — Delete a task

```bash
python scripts/manage_cron_task.py --action delete --task-id "abc-123"
```

Required: `--task-id`

## Cron Expression Examples

| Expression      | Meaning                  |
|-----------------|--------------------------|
| `0 9 * * 1-5`  | Weekdays at 9:00 AM      |
| `0 18 * * *`   | Every day at 6:00 PM     |
| `*/15 * * * *` | Every 15 minutes         |
| `0 9 * * 1`    | Every Monday at 9:00 AM  |
| `0 0 1 * *`    | First day of month at midnight |

## Workflow

1. Run `--action list` first to see existing tasks and get task IDs
2. Use the task ID from the list output for update/delete operations
3. After create/update/delete, the scheduler reloads automatically within 30 seconds

## Notes

- `--instruction` is what CodeGenAgent will execute when the task fires — write it as a clear, actionable instruction
- Task IDs are UUIDs assigned at creation; always use `list` to look them up
- The cron expression uses standard 5-field format: `minute hour day month weekday`
