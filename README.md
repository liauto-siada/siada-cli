# Siada CLI

![Siada CLI Screenshot](./docs/assets/siada-cli-screenshot.png)

This repository contains Siada CLI, a command-line AI workflow tool that provides specialized intelligent agents for code development, debugging, and automation tasks.

With Siada CLI you can:

- Fix bugs in large codebases through intelligent analysis and automated solutions.
- Generate new applications and components using specialized frontend and backend agents.
- Automate development workflows through intelligent code generation and testing.
- Execute system commands and interact with development environments.
- Seamlessly support multiple programming languages and frameworks.

## Quick Start

### Installation (Developer Mode)

1. **Prerequisites:** Ensure you have [Python 3.12](https://www.python.org/downloads/) or higher and [Poetry](https://python-poetry.org/docs/#installation) installed.

2. **Clone and Install:**
   ```bash
   git clone https://github.com/your-org/siada-agenthub.git
   cd siada-agenthub
   poetry install
   ```

3. **Run CLI:**
   ```bash
   # Method 1: Run with Poetry
   poetry run siada-cli
   
   # Method 2: Activate virtual environment then use (recommended)
   source $(poetry env info --path)/bin/activate
   siada-cli
   ```

### Configuration

1. **Configure Model:** Siada CLI provides multiple ways to configure AI models and providers. See the Model Configuration section for details:

   **Default/Configure via Configuration File**
   - The system reads default configuration from `agent_config.yaml` file
   - Current defaults: model `claude-sonnet-4`, provider `openrouter`
   - Edit the `llm_config` section in `agent_config.yaml` file:
   ```yaml
   llm_config:
     provider: "openrouter"                    
     model_name: "claude-sonnet-4"     # Change to your desired model
   ```
   - Set OPENROUTER_API_KEY
   ```bash
   # Required when using OpenRouter provider
   export OPENROUTER_API_KEY="your_openrouter_key"
   ```

2. **Choose Your Agent:** Select from available specialized agents:
   - `bugfix` - Bug fixing and debugging (non-interactive mode only)
   - `coder` - General code development  
   - `fegen` - Frontend code generation

   ```bash
   # Use a specific agent
   siada-cli --agent coder
   ```

You are now ready to use Siada CLI!

## Examples

### Activate Virtual Environment
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

**Exit Virtual Environment:**

```bash
# Exit virtual environment after use
deactivate
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
siada-cli --agent coder --model claude-sonnet-4 --prompt "Create a REST API endpoint"
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

# Non-interactive mode with a single prompt
siada-cli --prompt "Fix authentication errors in login.py"

# Use a different model
siada-cli --model claude-sonnet-4

# Use OpenRouter provider (requires API key setup)
siada-cli --provider openrouter

# Set color theme
siada-cli --theme dark

# Enable verbose output
siada-cli --verbose

# List all available models
siada-cli --list-models
```

## Slash Commands

In the CLI, you can use slash commands for additional functionality:

- `/shell` - Switch to shell mode to execute system commands (type `exit` or `quit` to exit shell mode)
- `/models` - List available AI models
- `/run <command>` or `!<command>` - Execute shell commands
- `/editor` - Open editor for multiline input
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

## Agent Types

### Bug Fix Agent (`--agent bugfix` or `--bugfix`) 
> **Only supports non-interactive mode!**

Specialized for identifying, analyzing, and fixing bugs in codebases. Provides detailed analysis and automated fix suggestions.

### Code Generation Agent (`--agent coder` or `--coder`)
General-purpose code development agent for creating new features, refactoring code, and implementing functionality in various programming languages.

### Frontend Generation Agent (`--agent fegen` or `--fegen`)
Focused on frontend development tasks, including React components, CSS styling, and user interface implementation.

## Configuration

### Model Configuration

**Method 1: Default Configuration**
   - The system reads default configuration from `agent_config.yaml` file
   - Current defaults: model `claude-sonnet-4`, provider `openrouter`

   **Method 2: Customize via Configuration File**
   - Edit the `llm_config` section in `agent_config.yaml` file:
   ```yaml
   llm_config:
     provider: "openrouter"
     model_name: "claude-sonnet-4"     # Change to your desired model
   ```

   **Method 3: Via Environment Variables**
   ```bash
   # Set model
   export SIADA_MODEL="claude-sonnet-4"
   
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
   > - **Model and Provider Association**: Different providers support different models, ensure provider compatibility when switching models
   > - **Complete Priority**: `Command line parameters` > `Environment variables (SIADA_ prefix)` > `Configuration file (agent_config.yaml)`
   > - **Provider Requirements**: When using `openrouter`, must set `OPENROUTER_API_KEY` environment variable

### Agent Configuration

Edit `agent_config.yaml` to customize agent behavior:

```yaml
agents:
  bugfix:
    class: "siada.agent_hub.coder.bug_fix_agent.BugFixAgent"
    description: "Specialized agent for code bug fixing"
    enabled: true

llm_config:
  provider: "openrouter"
  model_name: "claude-sonnet-4"
  repo_map_tokens: 8192
  repo_map_mul_no_files: 16
  repo_verbose: true
```

### Environment Variables

Set environment variables to configure behavior:

```bash
# Siada-specific settings (use SIADA_ prefix)
export SIADA_AGENT="bugfix"
export SIADA_MODEL="claude-sonnet-4"
export SIADA_THEME="dark"

# Required when using OpenRouter provider
export OPENROUTER_API_KEY="your_openrouter_key"

# Unset environment variables in current terminal session
unset SIADA_MODEL
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
- This is normal behavior as the command is installed in the virtual environment
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

## Acknowledgements

Siada CLI is built upon the foundation of numerous open source projects, and we extend our deepest respect and gratitude to their contributors.

For a complete list of open source projects and licenses used in Siada CLI, please see our [CREDITS.md](./CREDITS.md) file.

## License

Distributed under the MIT License. See [`LICENSE`](./LICENSE) for more information.
