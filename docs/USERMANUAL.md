# Siada CLI User Manual

**[简体中文](./zh-CN/USERMANUAL_zh.md) | English**

This user manual provides detailed usage instructions for Siada CLI, helping you make full use of this powerful AI workflow tool.

## Overview

Siada CLI is a professional command-line AI workflow tool designed specifically for code development, debugging, and automation tasks. It provides multiple intelligent agents, each optimized for specific development tasks.



## Configuration

### Model Configuration

**Method 1: Default Configuration**
   - The system reads default configuration from `agent_config.yaml` file
   - Current defaults: model `claude-sonnet-5`, provider `default`
   - On first launch, choose a provider and enter your API key. The selected
     endpoint and model are saved in `~/.siada-cli/conf.yaml`.

   **Method 2: Customize via Configuration File**
   - Regular Users
      - Edit configuration file `~/.siada-cli/conf.yaml`
         ```yaml
         llm_config:
            provider: "default"
            provider_id: "openai"
            model: "gpt-4o-mini"  # Use a model available at your endpoint
            base_url: "https://api.openai.com/v1"
            api_key: "YOUR_API_KEY"
         ```
   - Developer Mode
      - Edit the `llm_config` section in `agent_config.yaml` file:
         ```yaml
         llm_config:
            provider: "default"
            model_name: "claude-sonnet-5"     # Change to your desired model
         ```

   **Method 3: Via Environment Variables**
   ```bash
   # Set model
   export SIADA_MODEL="gpt-4o-mini"
   
   # Set provider
   export SIADA_PROVIDER="default"

   # Provider credentials for this terminal session
   export BASE_URL="https://api.openai.com/v1"
   export API_KEY="YOUR_API_KEY"
   ```

   **Method 4: Via Command Line Parameters (Highest Priority)**
   ```bash
   # Only change model (keep provider unchanged)
   siada-cli --model gpt-4o-mini
   
   # Change both model and provider
   siada-cli --model gpt-4o-mini --provider default
   
   # Only change provider (keep model unchanged)
   siada-cli --provider default
   ```

   > **Important Notes:**
   > - Model/provider priority: command line parameters > `SIADA_MODEL` /
   >   `SIADA_PROVIDER` > `~/.siada-cli/conf.yaml` > bundled defaults.
   > - Non-empty `BASE_URL` and `API_KEY` override the corresponding stored
   >   credentials. Both are required to sign in without the configuration prompt.

### Goal Verification Limit

The `/goal` verifier stops automatic continuation when it has no actionable
`nextAction`, or when the maximum number of consecutive failed verifier turns
is reached. Configure the limit in `~/.siada-cli/conf.yaml`:

```yaml
goal:
  max_turns: 6
```

The default is `6`. Two consecutive verifier system errors remain a separate,
faster safety breaker. Internal follow-up turns, including background task
results, do not reactivate a blocked goal; a new user message does. When there
is a goal to clear, `/goal clear` persists a hidden reminder in the session
history so the model knows not to resume it. If the history write fails, the
goal is still cleared and a warning is shown; the model may not receive the
reminder on its next turn.

### External Model Configuration

If you need to configure custom external models (such as privately deployed model services), please refer to the [External Model Configuration Guide](./external_model_configuration.md). This document provides detailed information on how to configure and use external models, including:
- Model naming conventions
- API connection configuration
- Protocol mapping explanation
- Configuration examples

### Sub-agent Model Configuration

Sub-agents use the parent session's model and provider by default. To select
a different model, add this section to `~/.siada-cli/conf.yaml`:

```yaml
sub_agent:
  enabled: true
  llm_config:
    model: "gpt-4o-mini"
```

When `provider` is omitted, the sub-agent inherits the parent's provider.
If a configured provider is unavailable in this distribution, it tries the
parent's active provider and then `default`, which uses your configured
`BASE_URL` and `API_KEY`. Available explicit providers retain priority.

### Agent Configuration (Developer Mode)

Edit `agent_config.yaml` to customize agent behavior:

```yaml
agents:
  coder:
    class: "siada.agent_hub.coder.code_gen_agent.CodeGenAgent"
    description: "General-purpose code development agent"
    enabled: true

llm_config:
  provider: "default"
  model_name: "claude-sonnet-5"
  repo_map_tokens: 8192
  repo_map_mul_no_files: 16
  repo_verbose: true
```

### Environment Variables

Set environment variables to configure behavior:

```bash
# Siada-specific settings (use SIADA_ prefix)
export SIADA_AGENT="coder"
export SIADA_MODEL="gpt-4o-mini"
export SIADA_THEME="dark"

# Unset environment variables in current terminal session
unset SIADA_MODEL
```

### Checkpoints Configuration

Siada CLI provides checkpoint tracking functionality to automatically save session states and enable recovery from previous points in your development workflow.

**What are Checkpoints?**
- Automatic snapshots of your session state after significant tool operations
- Includes conversation history, modified files, git state, API messages, and usage statistics
- Enables rollback to previous states and comparison between different points in time
- Automatic cleanup: keeps most recent checkpoints when limit is exceeded

**Enable Checkpoint Tracking:**

   **Method 1: Command Line Parameter**
   ```bash
   # Enable checkpoints when starting CLI
   siada-cli --checkpointing
   ```

   **Method 2: Environment Variable**
   ```bash
   # Enable checkpoints globally
   export SIADA_CHECKPOINTING=true
   siada-cli --agent coder
   ```

   **Method 3: Configuration File**
   
   edit `~/.siada-cli/conf.yaml`:
   ```yaml
   checkpoint_config:
     enable: true
   ```

**Checkpoint Usage:**
- Checkpoints are automatically created after tool operations like file edits and command executions
- Use `/restore <checkpoint_file>` to restore to a previous state
- Use `/undo <checkpoint_file>` to undo changes made by a checkpoint, restoring to the state before the checkpoint was created
- Use `/compare <checkpoint_file>` to see differences between current state and a checkpoint
  
**Storage Location:**
- Location: `~/.siada-cli/data/tmp/{project_hash}/checkpoints/{session_id}/`

**Maximum Checkpoint Files:**
- Default: 50 checkpoint files per session
- This limit ensures efficient disk space usage while maintaining sufficient history
- **Disable cleanup**: Set to 0 or negative value to disable automatic cleanup (keeps all checkpoints)

**Automatic Cleanup:**
- When checkpoint count exceeds max limit + 5, the system automatically deletes the 5 oldest checkpoints
- Example: With default limit of 50, cleanup triggers at 55 files and removes the oldest 5
- **Note**: Automatic cleanup is disabled when max_checkpoint_files is set to 0 or negative values
- This ensures disk space is managed efficiently while preserving recent work

### MCP Configuration

Siada CLI integrates MCP (Model Context Protocol) service to provide extended tools and resources for AI agents.

The MCP configuration loader reads JSON configuration sources only. MCP servers
provided by installed plugins are loaded separately by the plugin runtime.

**MCP Configuration File `~/.siada-cli/mcp_config.json`**

   Parameter descriptions:
   - `enabled`: Controls global/individual MCP server switches
   - `type`: Connection type (`stdio`/`http`/`sse`)

   Configuration file example:
   ```json
   {
      "enabled": true,
      "mcpServers": {
         "filesystem": {
            "enabled": true,
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocolserver-filesystem", "./"]
         }
      }
   }
   ```

**MCP Slash Commands**

   - `/mcp-server`: List all MCP servers
   - `/mcp-list`: List all MCP servers and their available tools

### .siadaignore Configuration

.siadaignore is a project-level configuration file used to inform Siada which files and directories should be ignored when analyzing the codebase. Similar to .gitignore, it uses pattern matching rules to specify files that should be excluded from Siada's context and operations.

**Note: This file needs to be created manually**

.siadaignore structure example
   ```bash
   # Dependencies
   node_modules/
   **/node_modules/
   .pnp
   .pnp.js

   # Build outputs
   /build/
   /dist/
   /.next/
   /out/

   # Testing
   /coverage/

   # Environment variables
   .env
   .env.local
   .env.development.local
   .env.test.local
   .env.production.local

   # Large data files
   *.csv
   *.xlsx
   ```

.siadaignore directory structure
   ```bash
   # .siadaignore file must be in the project root directory
   your-project/
   ├── .siadaignore
   ├── src/
   ├── docs/
   └── ...
   ```

## Usage Modes

Siada CLI supports two usage modes to meet different usage scenarios:

Interactive sessions use the Node.js terminal UI launched by `siada-cli`, with
an ACP-connected Python backend. The legacy Rich/prompt_toolkit interactive UI
is no longer supported. Non-interactive `--prompt` execution is unchanged.

### Non-Interactive Mode

**Features:**
- One-time execution: Execute a single task and automatically exit
- Stateless: Does not retain session context
- Use cases: Automation scripts, CI/CD pipelines, single task execution

**Usage:**
```bash
# Use --prompt parameter to trigger non-interactive mode
siada-cli --agent coder --prompt "Fix login errors in auth.py"

# Combine with other parameters
siada-cli --agent coder --model claude-sonnet-4.5 --prompt "Create a REST API endpoint"
```

### Interactive Mode

**Features:**
- Continuous conversation: Maintains session state after startup, allows continuous dialogue
- Context memory: AI remembers previous conversation content
- Real-time interaction: Supports slash commands, editor mode, and other advanced features
- Use cases: Exploratory programming, complex tasks, development work requiring multiple rounds of dialogue

**Usage:**
```bash
# Start directly (defaults to interactive mode)
siada-cli --agent coder
```

**Interactive Process:**
```
> Create a user management API
[AI response...]
> Add data validation to this API
[AI response...]
> Write some unit tests
[AI response...]
```

### Task Execution and Blockers

Siada executes tools within the requested task scope and the tool's permission
checks. The coding agent sends progress, results, and blockers through ordinary
assistant messages. You can send additional instructions while it works,
including a request to review a plan before execution. There is no separate
interactive question tool or planning-mode panel.

All `run_subtask` modes (normal, forked, background and recursive) run unattended
and report unresolved blockers to their calling agent.

### Browser Context in ACP Conversations

When a browser client supplies a leading `<browser-context>` preamble, the ACP
runtime separates it from the user's literal input. A turn with both page context
and browser-skill experience suggestions reaches the agent as three independent
user-role input items: `<user_input>` containing the user's message, a
`<system-reminder>` containing page context, and another containing experience
suggestions. Missing context items are omitted; ordinary prompts retain their
existing input shape.

These reminder tags mark low-trust runtime context, not a system wire role or
additional authorization. The context items are saved with the turn but hidden
from history replay. `@file` expansion processes the user's message without
merging the context items back into it.

## Daemon and Scheduled Tasks

### Daemon Process

Siada CLI automatically starts a background daemon process when launched. The daemon handles proactive tasks such as code analysis and scheduled job execution.

**Stop and check daemon status in non-interactive mode:**
```bash
# Stop the daemon
siada-cli --stop-daemon

# Check daemon status
siada-cli --daemon-status
```

### Scheduled Tasks (Cron Jobs)

You can set up scheduled tasks by simply telling Siada in natural language. The daemon will automatically manage execution.

**Examples:**
```
> Every day at 9:30 AM, compile the code according to the xxx document
> Run the test suite every day at 2:00 AM
```

Siada will configure the appropriate cron job and confirm the schedule with you.

## Command Line Options

```bash
# Use a specific agent
siada-cli --agent coder
# Supports abbreviations
siada-cli -a coder

# Non-interactive mode with a single prompt
siada-cli --prompt "Fix authentication errors in login.py"
# Supports abbreviations
siada-cli -p "Fix authentication errors in login.py"

# Use a different model
siada-cli --model claude-sonnet-4.5

# Set color theme
siada-cli --theme dark

# Enable verbose output
siada-cli --verbose

# List all available models
siada-cli --list-models
siada-cli --models

# Enable checkpoint tracking (for session recovery)
siada-cli --checkpointing

# Daemon management (non-interactive)
siada-cli --stop-daemon     # Stop the background daemon
siada-cli --daemon-status   # Show daemon status

## Version Check and Update
siada-cli --just-check-update  # Check version only, without executing update
siada-cli --upgrade            # Upgrade to the latest version immediately
siada-cli --check-update       # Check and prompt for updates on startup (enabled by default)

```

## Slash Commands

In the CLI, you can use slash commands for additional functionality:

- `!<command>` - Execute a single shell command without switching modes
- `/model` - Show model selector or switch model (`/model <model_name>`)
- `/editor` or `/edit` - Open editor for multiline input
- `/init [--force]` - Analyze the project and create a tailored `SIADA.md` file
- `/compact` - Compact conversation context; the terminal displays message counts and the number removed beneath the compaction status. The activity indicator shows compaction while it runs, then returns to model reasoning.
- `/restore <checkpoint_file>` - Restore session state from a checkpoint file (requires checkpoint tracking enabled)
- `/undo <checkpoint_file>` - Undo changes made by a checkpoint, restoring to the state before the checkpoint was created (requires checkpoint tracking enabled)
- `/compare <checkpoint_file>` - Compare current state with a checkpoint file to see differences
- `/context-file-refresh` - Refresh `SIADA.md` and `AGENTS.md` context files and show a content overview
- `/rule-status` - Show the discovered `siada_rule.md` hierarchy and its configuration
- `/status` - Display current session status (model, agent, session ID, and workspace)
- `/lang` - View current language configuration
  - `/lang zh` - Switch to Chinese
  - `/lang en` - Switch to English
- `/exit` - Exit the application

### Execute Shell Commands

Use the `!` prefix to execute a single system command from the prompt:

```bash
> !ls -la
> !git status
> !npm run dev
```

After the command finishes, the prompt returns to the conversation. The `/shell` command for persistent shell mode is disabled in this build.

### Language Configuration

**coder agent** supports language switching in **interactive mode** using slash commands

```bash
# Default language is English
# Display current language
/lang

# Switch current session language to Chinese
/lang zh
/lang zh-CN

# Switch current session language to English
/lang en
```

## Agent Types

### Code Generation Agent (`--agent coder` / `-a coder` / `--coder`)
General-purpose code development agent for creating new features, fixing bugs, refactoring code, and implementing functionality (including frontend tasks) in various programming languages.

### Custom Agents (`.agents/agents/`)
In addition to the built-in agent types, you can define your own named sub-agents in Markdown files under `.agents/agents/` (or `~/.siada-cli/agents/`). Each definition carries its own system prompt plus `tools`, `skills`, `mcpServers`, `background` and `effort` settings, and the main agent delegates to it through `run_subtask`. See the [Custom Agents Guide](./USER_AGENTS.md) for the file format, field reference, priority rules and examples.

Each `run_subtask` execution uses an isolated in-memory context that can be
compacted as it grows. Later SDK saves do not restore summarized task input.
Identical messages remain distinct, including repeated messages in inherited
(`fork`) history.

## Examples

### Activate Virtual Environment (Developer Mode Only)
First, enter the siada-cli project directory and activate the virtual environment:

```bash
# Enter project directory
cd ~/path/to/siada-cli

# Activate virtual environment (recommended method)
source $(poetry env info --path)/bin/activate

# Or use Poetry run (no need to activate environment)
# poetry run siada-cli
```

### Usage Examples

After activating the environment, you can choose between interactive mode or non-interactive mode to interact with AI agents.

**Interactive Mode:**

```bash
# Enter project directory
cd my-project/

# Start interactive mode
siada-cli --agent coder

# Then you can input prompts in the interactive interface
> Create a REST API server with user authentication using FastAPI
# AI will respond and you can continue the conversation...
> Add logging functionality to this API
```

**Non-Interactive Mode (One-time execution):**

```bash
# Execute a single task and exit (uses coder agent by default)
siada-cli --prompt "Create a user registration API"

# Specify a specific agent to execute tasks
siada-cli --agent coder --prompt "Fix authentication errors in login.py"
siada-cli --agent coder --prompt "Create a responsive navigation bar component using React and Tailwind CSS"
```

**Exit Virtual Environment (Developer Mode Only):**

```bash
# Exit virtual environment after use
deactivate
```

## Common Tasks

### Debug and Fix Code Issues

```text
> Analyze this error message and suggest a fix: [paste error]
```

```text
> Help me reproduce this intermittent bug that occurs during high load
```

### Code Generation and Development

The `edit_file` tool preserves LF/CRLF line endings when replacing or inserting
text. Added text uses the file's first line ending, or LF when none exists.
Untouched lines keep their original endings. Insertions preserve the existing
file's permissions, and new files keep the line endings supplied to `create`.

```text
> Implement a caching layer for the database queries in this service
```

```text
> Refactor this monolithic function into smaller, more maintainable pieces
```

### Frontend Development

```text
> Create a responsive dashboard layout with sidebar navigation
```

```text
> Add form validation to the user registration form
```

## Troubleshooting

### Common Issues

**Command not found:**
If running `siada-cli` directly shows command not found:
- This is normal behavior in developer mode as the command is installed in the virtual environment
- Refer to examples to activate the virtual environment

**Model API errors:**
- Check your internet connection

**Installation issues:**
- Ensure you have Python 3.12+ installed
- Install Poetry using the official installation method
- Try removing `poetry.lock` and re-running `poetry install`

**Agent not working:**
- Check if the agent is enabled in `agent_config.yaml`
- Verify the agent class path is correct
- Use `--verbose` flag to see detailed output

**Markdown file-edit display:**

Completed Markdown string replacements display as line diffs in both compact and expanded views, including resumed sessions. Embedded code blocks and blank lines are preserved. Incomplete edits remain in the tool text view until the stream finishes. Older unfenced display text with ambiguous `with:` separators falls back to the text view instead of showing a guessed diff.

**Patch context mismatch (`Invalid Context` / `Invalid EOF Context`):**

Native patch failures return recovery guidance:

- Old and context lines must match complete lines in the current file. The
  matcher does not interpret JSON fields or line fragments.
- Read the target region again and generate a patch from the current text.
  Exclude reader line numbers and truncation markers; do not repeat an unchanged
  failed patch.
- Matching tolerates leading/trailing whitespace and common Unicode punctuation
  or space differences while preserving untouched text. Different values and
  JSON formatting are not equivalent.
- Each native operation is validated before its writes. A batch is not a
  transaction: failed operations do not roll back successful ones, and the SDK
  may attempt later operations. Check each result and the current files before
  retrying.

For more detailed troubleshooting, check logs and use the `--verbose` flag for additional debug information.
