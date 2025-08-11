# Siada CLI 发布与安装系统

## 🚀 发布流程

### 前提条件

安装依赖：
```bash
poetry -C siada_internal install
```

### 发布命令

**测试环境（默认）：**
```bash
./siada_internal/scripts/publish.sh
```

**生产环境：**
```bash
SIADA_OIS=prod ./siada_internal/scripts/publish.sh
```

发布成功后会输出用户安装命令。

## 📦 用户安装

**测试环境：**
```bash
curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/test_remote_install.sh | sh
```

**生产环境：**
```bash
curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh
```

### 安装后配置

将 `~/.local/bin` 添加到 PATH：

```bash
# Bash/Zsh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Fish
echo 'fish_add_path $HOME/.local/bin' >> ~/.config/fish/config.fish
```

## 🔧 配置选项

### 环境变量

- **`SIADA_OIS`**：发布环境（`test` | `prod`，默认 `test`）
- **`SIADA_PYPI_INDEX`**：用户安装时可指定自定义 PyPI 镜像

### 自定义镜像示例

```bash
SIADA_PYPI_INDEX=https://pypi.org/simple curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/test_remote_install.sh | sh
```

## 🐛 故障排除

### 常见问题

1. **虚拟环境冲突**：删除 `~/.local/share/siada_cli_venv_3.12` 后重新安装
2. **命令不可用**：确保 `~/.local/bin` 已添加到 PATH
3. **权限问题**：检查用户对家目录的写权限

### 调试命令

```bash
# 检查安装状态
ls -la ~/.local/share/siada_cli_venv_3.12/
ls -la ~/.local/bin/siada-cli

# 测试命令
siada-cli --version
```
