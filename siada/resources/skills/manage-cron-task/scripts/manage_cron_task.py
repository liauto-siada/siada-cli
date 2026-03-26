#!/usr/bin/env python3
"""CLI wrapper for manage_cron_task_impl."""

import argparse
import sys
from siada.tools.proactive.manage_cron_task import manage_cron_task_impl


def main():
    parser = argparse.ArgumentParser(description="Manage crontab scheduled tasks")
    parser.add_argument("--action", required=True, choices=["create", "update", "delete", "list"])
    parser.add_argument("--task-id")
    parser.add_argument("--name")
    parser.add_argument("--cron-expr")
    parser.add_argument("--instruction")
    parser.add_argument("--enabled", choices=["true", "false"])
    parser.add_argument("--enabled-only", action="store_true", default=False)
    parser.add_argument("--sort-by", default="next_run", choices=["name", "created_at", "next_run"])

    args = parser.parse_args()

    enabled = None
    if args.enabled is not None:
        enabled = args.enabled == "true"

    try:
        result = manage_cron_task_impl(
            action=args.action,
            task_id=args.task_id,
            name=args.name,
            cron_expr=args.cron_expr,
            instruction=args.instruction,
            enabled=enabled,
            enabled_only=args.enabled_only,
            sort_by=args.sort_by,
        )
        print(result)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
