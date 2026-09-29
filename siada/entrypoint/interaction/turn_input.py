"""Shared shaping of SwitchEvent ``ai_analysis_prompt`` follow-up turns.

Two frontends consume the same contract — the terminal ``Controller`` (via
``Controller._build_pending_input_for_ai_analysis``) and the ACP runtime
(``SiadaTurnRunner.run_slash_command``): a SwitchEvent with
``goal_command=True`` must persist the *full* "/goal <objective>" text as the
next turn's user message, because ``SlashCommands.cmd_goal`` hands over only
the prefix-stripped objective. Keeping that shaping in one module keeps both
frontends in lockstep.
"""


def format_ai_analysis_followup(ai_analysis_prompt: str, goal_command: bool) -> str:
    """Return the follow-up text for an ``ai_analysis_prompt`` SwitchEvent.

    Non-goal callers (e.g. /init, /issue_fix) pass through unchanged.

    /goal is the one exception: cmd_goal hands us the stripped objective only,
    so re-adding the "/goal " prefix is what keeps the *fact of the /goal
    invocation* in the persisted conversation history — a bare objective would
    otherwise read like an ordinary user message on resume/replay.
    """
    if not goal_command:
        return ai_analysis_prompt
    return f"/goal {ai_analysis_prompt}"


def build_terminal_pending_input(ai_analysis_prompt: str, goal_command: bool) -> str | list:
    """Build the next-iteration ``pending_input`` for a terminal SwitchEvent
    that carries an ``ai_analysis_prompt`` (e.g. /init, /issue_fix, /goal).

    Terminal-specific envelope around ``format_ai_analysis_followup``:
    non-goal callers keep the bare string; /goal comes back as a
    Responses-API input list.
    """
    text = format_ai_analysis_followup(ai_analysis_prompt, goal_command)
    if not goal_command:
        return text

    # List shape: TurnFactory routes list inputs straight to ConversationTurn
    # (CommandTurn.can_handle()/is_command() only inspect strings), so the
    # literal "/goal " text can never be re-parsed as a new slash command on
    # the next loop iteration.
    #
    # Why the wrap must happen here: building the list ahead of
    # ConversationTurn's own isinstance(str) wrap check means that check never
    # fires for /goal (the value is already list-shaped by the time it gets
    # there) — so wrapping here, before embedding into the list, is the only
    # way /goal's kickoff turn keeps the <user_input>...</user_input> markers
    # every other entry point applies to literal human-authored text.
    from siada.services.memory.holographic.marker import wrap_user_input

    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": wrap_user_input(text),
                }
            ],
        }
    ]