# Siada CLI User Manual

**[简体中文](./zh-CN/USERMANUAL_zh.md) | English**

This user manual provides detailed usage instructions for Siada CLI, helping you make full use of this powerful AI workflow tool.

## Overview

Siada CLI is a professional command-line AI workflow tool designed specifically for code development, debugging, and automation tasks. It provides multiple intelligent agents, each optimized for specific development tasks.



## Configuration

### Model Configuration

**Method 1: Default Configuration**
   - The system reads default configuration from `agent_config.yaml` file
   - Current defaults: model `claude-sonnet-4.5`, provider `openrouter`

   **Method 2: Customize via Configuration File**
   - Regular Users
      - Edit configuration file `~/.siada-cli/conf.yaml`
         ```bash
         # 1. Create configuration file in user home directory
         cd ~
         mkdir -p ~/.siada-cli
         touch ~/.siada-cli/conf.yaml

         # 2. Configuration file content example
         llm_config:
            model: "claude-sonnet-4.5"          # Change to your desired model
            provider: "openrouter"
         ```
   - Developer Mode
      - Edit the `llm_config` section in `agent_config.yaml` file:
         ```yaml
         llm_config:
            provider: "openrouter"
            model_name: "claude-sonnet-4.5"     # Change to your desired model
         ```

   **Method 3: Via Environment Variables**
   ```bash
   # Set model
   export SIADA_MODEL="claude-sonnet-4.5"
   
   # Set provider
   export SIADA_PROVIDER="openrouter"

   # Required when using OpenRouter provider
   export OPENROUTER_API_KEY="your_openrouter_key"
   ```

   **Method 4: Via Command Line Parameters (Highest Priority)**
   ```bash
   # Only change model (keep provider unchanged)
   siada-cli --model claude-sonnet-4
   
   # Change both model and provider
   siada-cli --model gpt-4.1 --provider openrouter
   
   # Only change provider (keep model unchanged)
   siada-cli --provider openrouter
   ```

   > **Important Notes:**
   > - **Complete Priority**: `Command line parameters` > `Environment variables (SIADA_ prefix)` > `Configuration file (agent_config.yaml)`
   > - **Provider Requirements**: When using `openrouter`, must set `OPENROUTER_API_KEY` environment variable

### External Model Configuration

If you need to configure custom external models (such as privately deployed model services), please refer to the [External Model Configuration Guide](./external_model_configuration.md). This document provides detailed information on how to configure and use external models, including:
- Model naming conventions
- API connection configuration
- Protocol mapping explanation
- Configuration examples

### Agent Configuration (Developer Mode)

Edit `agent_config.yaml` to customize agent behavior:

```yaml
agents:
  bugfix:
    class: "siada.agent_hub.coder.bug_fix_agent.BugFixAgent"
    description: "Specialized agent for code bug fixing"
    enabled: true

llm_config:
  provider: "openrouter"
  model_name: "claude-sonnet-4.5"
  repo_map_tokens: 8192
  repo_map_mul_no_files: 16
  repo_verbose: true
```

### Environment Variables

Set environment variables to configure behavior:

```bash
# Siada-specific settings (use SIADA_ prefix)
export SIADA_AGENT="bugfix"
export SIADA_MODEL="claude-sonnet-4.5"
export SIADA_THEME="dark"

# Required when using OpenRouter provider
export OPENROUTER_API_KEY="your_openrouter_key"

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

### Non-Interactive Mode

**Features:**
- One-time execution: Execute a single task and automatically exit
- Stateless: Does not retain session context
- Use cases: Automation scripts, CI/CD pipelines, single task execution

**Usage:**
```bash
# Use --prompt parameter to trigger non-interactive mode
siada-cli --agent bugfix --prompt "Fix login errors in auth.py"

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

# Use OpenRouter provider (requires API key setup)
siada-cli --provider openrouter

# Set color theme
siada-cli --theme dark

# Enable verbose output
siada-cli --verbose

# List all available models
siada-cli --list-models
siada-cli --models

# Enable checkpoint tracking (for session recovery)
siada-cli --checkpointing

## Version Check and Update
siada-cli --just-check-update  # Check version only, without executing update
siada-cli --upgrade            # Upgrade to the latest version immediately
siada-cli --check-update       # Check and prompt for updates on startup (enabled by default)

```

## Slash Commands

In the CLI, you can use slash commands for additional functionality:

- `/shell` - Switch to shell mode to execute system commands (type `exit` or `quit` to exit shell mode)
- `/models` - List available AI models
- `/run <command>` or `!<command>` - Execute shell commands
- `/editor` or `/edit` - Open editor for multiline input
- `/multiline-mode` - Toggle multiline mode (changes behavior of Enter and Meta+Enter keys)
  - Enter key for line break
  - Meta+Enter key to end multiline mode and send content to the model
- `/init [--force]` - Analyze the project and create a tailored siada.md file
- `/restore <checkpoint_file>` - Restore session state from a checkpoint file (requires checkpoint tracking enabled)
- `/undo <checkpoint_file>` - Undo changes made by a checkpoint, restoring to the state before the checkpoint was created (requires checkpoint tracking enabled)
- `/compare <checkpoint_file>` - Compare current state with a checkpoint file to see differences
- `/memory-refresh` - Refresh user memory content from siada.md file
- `/memory-status` - Display current user memory status (file info, size, loaded status)
- `/status` - Display current session status (model, agent, session ID, and workspace)
- `/lang` - View current language configuration
  - `/lang zh` - Switch to Chinese
  - `/lang en` - Switch to English
- `/exit` or `/quit` - Exit the application

### Shell Mode Usage Guide

Siada CLI provides two ways to execute system commands:

#### Method 1: Use `/shell` to switch to shell mode
Switch to persistent shell mode where you can continuously execute multiple system commands:

```bash
> /shell
# After entering shell mode, you can execute multiple commands
ls -la
cd my-project
npm install
git status
# Use exit or quit to exit shell mode
exit
```

#### Method 2: Use `!` prefix to execute commands directly
Execute single system commands directly in interactive mode without switching modes:

```bash
> !ls -la
> !git status
> !npm run dev
```

Differences between the two methods:
- **`/shell`**: Suitable for scenarios requiring continuous execution of multiple system commands, switch once and use persistently
- **`!<command>`**: Suitable for occasionally executing single system commands, returns to AI conversation mode immediately after execution

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

### Bug Fix Agent (`--agent bugfix` / `-a bugfix` / `--bugfix`) 
> **Only supports non-interactive mode!**

Specialized for identifying, analyzing, and fixing bugs in codebases. Provides detailed analysis and automated fix suggestions.

### Code Generation Agent (`--agent coder` / `-a coder` / `--coder`)
General-purpose code development agent for creating new features, refactoring code, and implementing functionality in various programming languages.

### Frontend Generation Agent (`--agent fegen` / `-a fegen` / `--fegen`)
Focused on frontend development tasks, including React components, CSS styling, and user interface implementation.

## Examples

### Activate Virtual Environment (Developer Mode Only)
First, enter the siada-agenthub project directory and activate the virtual environment:

```bash
# Enter project directory
cd ~/path/to/siada-agenthub

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
siada-cli --agent bugfix --prompt "Fix authentication errors in login.py"
siada-cli --agent fegen --prompt "Create a responsive navigation bar component using React and Tailwind CSS"
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
- If using OpenRouter provider, ensure API key is set correctly
- If using OpenRouter provider, verify your account has sufficient credits

**Installation issues:**
- Ensure you have Python 3.12+ installed
- Install Poetry using the official installation method
- Try removing `poetry.lock` and re-running `poetry install`

**Agent not working:**
- Check if the agent is enabled in `agent_config.yaml`
- Verify the agent class path is correct
- Use `--verbose` flag to see detailed output

For more detailed troubleshooting, check logs and use the `--verbose` flag for additional debug information.
