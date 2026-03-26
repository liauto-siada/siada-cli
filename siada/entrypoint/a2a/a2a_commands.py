from typing import Optional


def handle_a2a_commands(args, io) -> Optional[int]:
    """Handle --api-server and --stop-api-server commands.

    Called only when at least one of the two flags is set and io is already initialised.
    Returns an exit code, or None if neither flag matched.
    """
    if args.stop_api_server:
        from siada.agent_hub.a2a.server.server_lifecycle import stop_a2a_server
        return stop_a2a_server(io)

    if args.api_server:
        from siada.agent_hub.a2a.server.server_lifecycle import run_a2a_server_core
        return run_a2a_server_core(args, io)

    return None
