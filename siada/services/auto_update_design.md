# auto_update.py 设计说明

本文档解释 `auto_update.py` 中版本化 venv 自动更新机制的设计原理与完整执行流程。

---

## 一、为什么需要版本化 venv？

旧方案（in-place pip install）的问题：

- pip 在更新包时会直接替换 `site-packages/` 下的文件
- 如果用户正好在使用 siada-cli，Python 进程已经把旧版本的 `.py`/`.so` 加载到内存
- pip 删除旧文件、写入新文件的过程中，可能出现**模块找不到、行为混乱**等问题
- 即使 pip 报告成功（exit 0），实际版本也可能没变（被 cache 或依赖冲突阻止）

新方案参考 Claude Code 的做法：**版本目录隔离 + 硬链接克隆 + 原子符号链接切换**。

---

## 二、磁盘目录结构

```
~/.local/share/
├── siada_cli_venv_3.12              ← 符号链接（migration 后）
│                                       → 指向 siada_cli_versions/<当前版本>/
└── siada_cli_versions/              ← 版本目录池（_SIADA_VERSIONS_DIR_NAME）
    ├── 1.7.2/                       ← 旧版本（会被清理）
    └── 1.7.3/                       ← 新版本（真实目录）
        ├── bin/python
        ├── lib/python3.12/site-packages/siada/
        └── .siada_version
```

首次迁移前，`siada_cli_venv_3.12` 是真实目录；首次更新后变为符号链接。

---

## 三、关键概念：inode vs 路径

理解本方案的核心是区分**路径**和 **inode**：

- **路径**：文件系统中的名字（如 `/usr/lib/foo.py`），可以被重命名、删除、替换
- **inode**：磁盘上文件数据的实际编号，进程打开文件后持有的是 inode 引用

```
路径 /a/foo.py  →  inode #1001  →  磁盘数据（v1.7.2 代码）
路径 /a/foo.py  →  inode #2001  →  磁盘数据（v1.7.3 代码）（pip 替换后）

正在运行的进程：持有的是 inode #1001，不管路径怎么变，读到的都是 v1.7.2
```

**结论**：只要不修改旧 venv 目录里的文件（只在克隆里安装新版本），运行中的进程就完全不受影响。

---

## 四、完整更新流程举例（v1.7.2 → v1.7.3）

### 初始状态

```
~/.local/share/
└── siada_cli_venv_3.12/          ← 真实目录（旧安装）
    ├── bin/python
    ├── lib/.../siada/__init__.py  ← inode #1001（v1.7.2）
    └── .siada_version             ← "siada_cli-1.7.2-py3-none-any.whl"
```

用户正在进行对话，进程 `sys.executable = ~/.local/share/siada_cli_venv_3.12/bin/python`，
已把 v1.7.2 的代码加载到内存（inode #1001）。

---

### Step 1：`_get_venv_paths()` — 确定路径

```python
exe       = ~/.local/share/siada_cli_venv_3.12/bin/python
venv_link = ~/.local/share/siada_cli_venv_3.12      # 不 resolve，保留符号链接路径
venv_parent = ~/.local/share/
versions_dir = ~/.local/share/siada_cli_versions/
```

**关键**：`exe.parent.parent` 不调用 `.resolve()`，保留符号链接本身的路径，这样后续才能替换它。

---

### Step 2：`_clone_venv_hardlink()` — 硬链接克隆

执行系统命令：

```bash
cp -al ~/.local/share/siada_cli_venv_3.12 \
       ~/.local/share/siada_cli_versions/1.7.3
```

克隆后状态：

```
siada_cli_venv_3.12/lib/.../siada/__init__.py   → inode #1001
siada_cli_versions/1.7.3/lib/.../siada/__init__.py → inode #1001  ← 同一个！
```

- `cp -al`：`-a` 递归保留属性，`-l` 用硬链接代替真实复制
- 克隆几乎**瞬时完成**，不占额外磁盘空间
- 两个目录共享相同 inode，磁盘只有一份数据

---

### Step 3：pip install 进克隆

```bash
~/.local/share/siada_cli_versions/1.7.3/bin/python \
    -m pip install siada_cli-1.7.3-py3-none-any.whl
```

pip 写入 v1.7.3 的文件时，**在克隆目录里创建全新的 inode**：

```
siada_cli_versions/1.7.3/lib/.../siada/__init__.py → inode #2001（v1.7.3 新文件）
siada_cli_venv_3.12/lib/.../siada/__init__.py      → inode #1001（v1.7.2 未动！）
```

用户的 session 进程仍然持有 inode #1001，**正在进行的对话完全不受干扰**。

---

### Step 4：`_verify_installed_version_in_venv()` — 在克隆里验证版本

```bash
~/.local/share/siada_cli_versions/1.7.3/bin/python \
    -m pip show siada-cli
# → Version: 1.7.3  ✅
```

用**克隆自己的 Python**（不是 `sys.executable`）查询，确认新版本确实写进了克隆。

---

### Step 5：`_atomic_symlink_update()` — 原子切换符号链接

此时 `siada_cli_venv_3.12` 是真实目录（首次迁移），走备份分支：

```python
# 1. 把旧目录原子 rename 为备份（几乎瞬时）
os.rename(
    ~/.local/share/siada_cli_venv_3.12,
    ~/.local/share/siada_cli_venv_3.12.old.12345   # 进程 pid=12345
)

# 2. 创建指向新版本的符号链接
os.symlink(
    ~/.local/share/siada_cli_versions/1.7.3,
    ~/.local/share/siada_cli_venv_3.12
)
```

切换后磁盘状态：

```
~/.local/share/
├── siada_cli_venv_3.12  →  siada_cli_versions/1.7.3/   ← 符号链接（新版本）
├── siada_cli_venv_3.12.old.12345/                       ← 旧目录备份
└── siada_cli_versions/
    └── 1.7.3/
```

- **此刻起**：新启动的 siada-cli 进程沿符号链接拿到 v1.7.3
- **正在运行的 session**：`sys.executable` 解析后指向备份目录，inode 不变，一切正常

下次更新（1.7.3 → 1.7.4）时，`siada_cli_venv_3.12` 已是符号链接，走原子 rename 分支：

```python
# 创建临时符号链接
os.symlink(siada_cli_versions/1.7.4, siada_cli_venv_3.12.tmp.99999)

# 原子 rename（POSIX 保证原子性，不存在中间状态）
os.rename(siada_cli_venv_3.12.tmp.99999, siada_cli_venv_3.12)
```

---

### Step 6：`_update_version_file()` — 写版本标记文件

```python
# 写入新 venv 的根目录（通过已切换的符号链接访问）
~/.local/share/siada_cli_venv_3.12/.siada_version
# 内容："siada_cli-1.7.3-py3-none-any.whl"
```

---

### Step 7：`_cleanup_old_versions()` — 清理旧版本目录

`siada_cli_versions/` 当前内容（假设有两个版本）：

```
siada_cli_versions/
├── 1.7.2/   ← 候选删除
└── 1.7.3/   ← 新装，在 protect 列表
```

保护规则（双重保护）：
1. 调用者传入的 `protect=[new_venv_dir]`（刚安装的版本）
2. 自动保护正在运行的 venv：`Path(sys.executable).resolve().parent.parent`

`1.7.2/` 没有任何保护，且超出 `_VERSION_RETENTION_COUNT=2`，执行 `shutil.rmtree(1.7.2/)`。

最终磁盘状态：

```
~/.local/share/
├── siada_cli_venv_3.12  →  siada_cli_versions/1.7.3/
└── siada_cli_versions/
    └── 1.7.3/
```

---

## 五、整体时间轴

```
时间线 ─────────────────────────────────────────────────────────▶

用户 session：  [────── 对话进行中，持有 inode #1001（v1.7.2）──────▶]

daemon 后台：        [克隆]  [pip安装]  [验证]  [切链接]  [清理]
                      ↑                           ↑
                  用户完全无感知            符号链接瞬间切换
                                           下次启动拿到 v1.7.3
```

---

## 六、失败处理（不再 fallback）

**设计原则：版本化克隆路径任一步失败，直接打日志 + `return False`，不做 in-place 降级。**

历史上有过 `_install_inplace()` 的兜底路径——直接在当前正在运行的 venv 里 `pip install --force-reinstall`。但实测发现两个严重问题：

1. **broken symlink 场景**：当前 venv 的 `sys.executable` 经 broken symlink 解析失败时，`_install_inplace` 内部的 `uv pip install --python <broken>` 一样会全部失败，且会把 5 个镜像挨个重试一遍，刷出大量误导性错误日志。
2. **半途崩溃风险**：原地升级一旦中途出错，运行中的 daemon 进程的 site-packages 已被部分覆写，后续延迟 import 会拉到不一致的字节码 → `ModuleNotFoundError`、段错误等连锁反应（参见现网 1.7.2→1.7.3 故障日志）。

因此现在所有失败场景一律 fail-fast：

| 失败场景 | 处理方式 |
|---------|---------|
| `_get_venv_paths()` 异常 | log error + `return False, err_msg` |
| 检测到 broken symlink（venv link 目标不存在） | log error + `return False, err_msg` |
| `cp -al` 克隆失败（fs 不支持 hardlink / 磁盘满） | log error + `return False, err_msg` |
| pip install 失败 / 版本验证失败 | 清理克隆，`return False, errors` |
| 符号链接切换失败 | 清理克隆，`return False, err_msg` |

失败后 `DaemonAutoUpdater._check_with_lock` 会把 state 写成 `status="failed"` 并记录 `last_error`；daemon 进程**继续以当前版本健康运行**，30 分钟后自动再尝试一轮。需要修复时由用户/运维重跑安装脚本即可：

```sh
curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh
```

---

## 七、关键设计决策

| 决策 | 原因 |
|------|------|
| `cp -al` 而非 `cp -a` | 硬链接克隆瞬时完成、不占额外空间；pip 写新文件时自动产生新 inode |
| `exe.parent.parent` 不 resolve | 保留符号链接路径，才能替换符号链接本身 |
| `os.rename()` 原子替换 | POSIX 保证原子性，不存在"链接指向哪里都不对"的瞬间 |
| 首次迁移备份旧目录而非删除 | 安全回退，旧 session 的进程路径解析后仍有效 |
| 双重保护（protect + running_venv） | 防止正在使用的版本被清理 |
| `_VERSION_RETENTION_COUNT = 2` | 保留当前 + 上一个版本，便于问题排查，不过多占用磁盘 |
