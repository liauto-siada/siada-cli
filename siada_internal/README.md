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

### 开发者环境变量

- **`SIADA_OIS`**：发布环境
  - `test`：测试环境（默认）
  - `prod`：生产环境
  - 示例：`SIADA_OIS=prod ./siada_internal/scripts/publish.sh`

- **`SIADA_DIST_DIR`**：wheel 文件目录
  - 默认：`dist/`（项目根目录下）
  - 示例：`SIADA_DIST_DIR=/path/to/custom/dist python pack_pipeline.py`

### 用户安装环境变量

- **`SIADA_PYPI_INDEX`**：自定义 PyPI 镜像
  - 默认：`https://pypi.tuna.tsinghua.edu.cn/simple`
  - 支持任何兼容的 PyPI 镜像源
  - 示例：
    ```bash
    # 使用官方源
    SIADA_PYPI_INDEX=https://pypi.org/simple curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/test_remote_install.sh | sh
    
    # 使用阿里云源
    SIADA_PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/test_remote_install.sh | sh
    ```

### PATH 配置

安装完成后需要将 `~/.local/bin` 添加到 PATH：

```bash
# Bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Zsh 
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 检查是否生效
echo $PATH | grep -o "$HOME/.local/bin"
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
