# Agent Configuration File Usage Guide

## Overview

This project uses the configuration file `agent_config.yaml` to manage agent registration and configuration, implementing a flexible agent management mechanism.

## Configuration File Structure

The configuration file is located in the project root directory: `agent_config.yaml`

```yaml
agents:
  # Agent name (lowercase, supports underscores)
  agent_name:
    class: "full.class.import.path"
    description: "Agent description"
    enabled: true/false
```

## Currently Supported Agents

### BugFixAgent
- **Name**: `bugfix`
- **Class Path**: `siada.agent_hub.coder.bug_fix_agent.BugFixAgent`
- **Description**: Specialized agent for code bug fixing
- **Status**: Enabled

### CoderAgent (Planned)
- **Name**: `coder`
- **Class Path**: Not implemented yet
- **Description**: General-purpose code development agent
- **Status**: Disabled

## Usage

### Basic Usage

```python
from siada.services.siada_runner import SiadaRunner

# Get BugFixAgent instance
agent = await SiadaRunner.get_agent("bugfix")

# Supports multiple name formats
agent = await SiadaRunner.get_agent("BugFix")    # Uppercase
agent = await SiadaRunner.get_agent("bug_fix")   # Underscore
agent = await SiadaRunner.get_agent("bug-fix")   # Hyphen
```

### Error Handling

```python
try:
    agent = await SiadaRunner.get_agent("unknown")
except ValueError as e:
    print(f"Agent not found: {e}")

try:
    agent = await SiadaRunner.get_agent("coder")  # Disabled agent
except ValueError as e:
    print(f"Agent disabled: {e}")
```

## Adding New Agents

To add a new agent, you only need to:

1. **Implement Agent Class**: Create a new class that inherits from `Agent`
2. **Update Configuration File**: Add configuration in `agent_config.yaml`

### Example: Adding a New Agent

1. Create agent class file: `siada/agent_hub/new_agent.py`
```python
from agents import Agent

class NewAgent(Agent):
    def __init__(self):
        super().__init__(name="NewAgent", ...)
```

2. Update `agent_config.yaml`:
```yaml
agents:
  bugfix:
    class: "siada.agent_hub.coder.bug_fix_agent.BugFixAgent"
    description: "Specialized agent for code bug fixing"
    enabled: true
  
  # New agent
  newagent:
    class: "siada.agent_hub.new_agent.NewAgent"
    description: "New functionality agent"
    enabled: true
```

3. Use the new agent:
```python
agent = await SiadaRunner.get_agent("newagent")
```

## Configuration Options

- **class**: Full import path of the Agent class
  - Format: `module.path.ClassName`
  - If `null`, indicates the agent is not implemented yet
  
- **description**: Description of the agent
  - Used for documentation and debugging
  
- **enabled**: Whether the agent is enabled
  - `true`: Enabled, can be obtained via `get_agent()`
  - `false`: Disabled, will throw an exception when called

## Features

- ✅ **Dynamic Loading**: Supports runtime dynamic import of agent classes
- ✅ **Flexible Naming**: Supports multiple name formats (case-insensitive, underscores, hyphens)
- ✅ **State Management**: Supports enabling/disabling agents
- ✅ **Error Handling**: Comprehensive exception handling mechanism
- ✅ **Extensibility**: Easy to add new agent types
- ✅ **Configuration-Driven**: No code changes needed, just update configuration file

## Notes

1. **Configuration File Path**: Configuration file must be located in the project root directory
2. **Class Import Path**: Ensure the agent class import path is correct
3. **Dependency Management**: Dependencies for new agents need to be properly installed
4. **Naming Convention**: Agent names should use lowercase letters and underscores

## Testing

Run the test suite to ensure everything works correctly:

```bash
# Run all agent tests
python run_agent_tests.py

# Run specific tests
python -m pytest tests/agent/test_get_agent.py -v
```

The test suite includes 15 comprehensive test cases covering:
- Basic functionality
- Name variations and case sensitivity
- Error handling for disabled/unknown agents
- Configuration loading and validation
- Dynamic class importing
