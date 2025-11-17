# Siada CLI

**[简体中文](./docs/zh-CN/README_zh.md) | English**

![Siada CLI Screenshot](./docs/assets/siada-cli-screenshot.png)

This repository contains Siada CLI, a command-line AI workflow tool that provides specialized intelligent agents for code development, debugging, and automation tasks.

With Siada CLI you can:

- Fix bugs in large codebases through intelligent analysis and automated solutions.
- Generate new applications and components using specialized frontend and backend agents.
- Automate development workflows through intelligent code generation and testing.
- Execute system commands and interact with development environments.
- Seamlessly support multiple programming languages and frameworks.

## Installation/Update

### System Requirements
- MAC, Linux
- GCC 11+
- uv

### Installation

1. Install uv
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Install siada-cli
   ```bash
   uv tool install --force --python python3.12 --compile --with pip siada-cli@latest
   ```
   If the siada-cli directory is not present on the PATH, run the follow command to update the shell
   ```bash
   uv tool update-shell
   ```
### Update
   ```bash
   uv tool upgrade siada-cli
   ```
### Uninstall
   ```bash
   uv tool uninstall siada-cli
   ```

## Installation (Developer Mode)

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

## User Guide

For detailed usage instructions and advanced features, please refer to our [User Manual](docs/USERMANUAL.md), which includes:

- Detailed configuration instructions
- Usage modes and command-line options
- Slash command usage guide
- Agent type explanations
- Practical usage examples
- Troubleshooting guide



## Contributing

We welcome contributions to Siada CLI! Whether you want to fix bugs, add new features, improve documentation, or suggest enhancements, your contributions are greatly appreciated.

To get started with contributing, please read our [Contributing Guide](./docs/CONTRIBUTING.md) which includes:

- Our project vision and development goals
- Project directory structure and development guidelines
- Pull request guidelines and best practices
- Code organization principles

Before submitting any changes, please make sure to check our issue tracker and follow the contribution workflow outlined in the guide.

## Acknowledgements

Siada CLI is built upon the foundation of numerous open source projects, and we extend our deepest respect and gratitude to their contributors.

Special thanks to the [OpenAI Agent SDK](https://github.com/openai/openai-agent-sdk) for providing the foundational framework that powers our intelligent agent capabilities.

For a complete list of open source projects and licenses used in Siada CLI, please see our [CREDITS.md](./docs/CREDITS.md) file.

## License

Distributed under the Apache-2.0 License. See [`LICENSE`](LICENSE) for more information.

## DISCLAIMERS
See [disclaimers.md](./disclaimers.md)

----
<div align="center">
Built with ❤️ by Li Auto Code Intelligence Team and the open source community
</div>
