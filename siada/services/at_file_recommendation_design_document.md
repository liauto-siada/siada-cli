# @ 文件推荐功能设计文档

## 文档概述

本文档详细描述了 Gemini CLI 中 @ 文件推荐功能的完整技术规范，包括核心算法、系统架构、用户交互模式和实现细节。该文档旨在为 Python 版本的实现提供完整的技术指导。

**版本**: 1.0  
**创建日期**: 2025-01-06  
**目标**: 为 Python 实现提供完整的技术规范

---

## 1. 功能概述

### 1.1 核心功能
@ 文件推荐功能是一个实时文件路径自动完成系统，当用户在输入框中键入 `@` 字符后，系统会：
- 实时搜索和推荐可用的文件和目录
- 支持递归文件搜索和模糊匹配
- 提供智能过滤（.gitignore、.geminiignore）
- 支持键盘导航和自动完成

### 1.2 用户场景
```
用户输入: "@"           → 显示当前目录下的所有文件
用户输入: "@src"        → 显示以 "src" 开头的文件和目录
用户输入: "@src/"       → 显示 src 目录下的文件
用户输入: "@config.j"   → 显示匹配 "config.j" 的文件（如 config.json）
```

---

## 2. 系统架构

### 2.1 核心组件架构

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   InputHandler  │───▶│  CompletionEngine │───▶│ SuggestionsList │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        │
        ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   TextBuffer    │    │ FileDiscoveryService │    │    UI Display   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │
        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐
│  CursorTracker  │    │   FilterService  │
└─────────────────┘    └──────────────────┘
```

### 2.2 数据流图

```
用户输入 "@src" 
    ↓
[触发检测] - 检查光标位置和 @ 字符
    ↓
[路径解析] - 解析部分路径 "src"
    ↓
[文件搜索] - 搜索匹配的文件/目录
    ↓
[过滤处理] - 应用 gitignore/geminiignore 规则
    ↓
[排序优化] - 按深度、类型、名称排序
    ↓
[UI 显示] - 显示推荐列表
    ↓
[用户选择] - Tab/Enter 选择，上下箭头导航
```

---

## 3. 核心算法

### 3.1 触发检测算法

**激活条件判断逻辑**:

```python
def is_completion_active(text: str, cursor_row: int, cursor_col: int, lines: List[str]) -> bool:
    """
    检查是否应该激活 @ 文件推荐功能
    
    Args:
        text: 完整输入文本
        cursor_row: 光标行号
        cursor_col: 光标列号
        lines: 文本行列表
    
    Returns:
        bool: 是否激活推荐功能
    """
    # 如果是斜杠命令，优先处理
    if text.strip().startswith('/'):
        return True
    
    # 获取当前行
    current_line = lines[cursor_row] if cursor_row < len(lines) else ""
    code_points = list(current_line)  # Unicode 代码点数组
    
    # 从光标位置向前搜索
    for i in range(cursor_col - 1, -1, -1):
        char = code_points[i]
        
        if char == ' ':
            # 检查是否为转义空格
            backslash_count = 0
            j = i - 1
            while j >= 0 and code_points[j] == '\\':
                backslash_count += 1
                j -= 1
            
            # 偶数个反斜杠表示未转义的空格
            if backslash_count % 2 == 0:
                return False
                
        elif char == '@':
            # 找到 @ 字符，激活推荐
            return True
    
    return False
```

### 3.2 路径解析算法

```python
def parse_at_command_path(text: str) -> Tuple[str, str, str]:
    """
    解析 @ 命令中的路径信息
    
    Args:
        text: 输入文本
    
    Returns:
        Tuple[基础目录, 路径前缀, 原始部分路径]
    """
    at_index = text.rfind('@')
    if at_index == -1:
        return ".", "", ""
    
    partial_path = text[at_index + 1:]
    last_slash_index = partial_path.rfind('/')
    
    if last_slash_index == -1:
        base_dir_relative = "."
        prefix = unescape_path(partial_path)
    else:
        base_dir_relative = partial_path[:last_slash_index + 1]
        prefix = unescape_path(partial_path[last_slash_index + 1:])
    
    return base_dir_relative, prefix, partial_path
```

### 3.3 文件搜索算法

#### 3.3.1 递归搜索算法

```python
async def find_files_recursively(
    start_dir: str,
    search_prefix: str,
    file_discovery: FileDiscoveryService,
    filter_options: FilterOptions,
    current_relative_path: str = "",
    depth: int = 0,
    max_depth: int = 10,
    max_results: int = 50
) -> List[Suggestion]:
    """
    递归搜索文件和目录
    
    Args:
        start_dir: 起始搜索目录
        search_prefix: 搜索前缀
        file_discovery: 文件发现服务
        filter_options: 过滤选项
        current_relative_path: 当前相对路径
        depth: 当前递归深度
        max_depth: 最大递归深度
        max_results: 最大结果数量
    
    Returns:
        List[Suggestion]: 建议列表
    """
    if depth > max_depth:
        return []
    
    lower_search_prefix = search_prefix.lower()
    found_suggestions = []
    
    try:
        entries = await fs.readdir(start_dir, with_file_types=True)
        
        for entry in entries:
            if len(found_suggestions) >= max_results:
                break
            
            entry_path_relative = os.path.join(current_relative_path, entry.name)
            entry_path_from_root = os.path.relpath(
                os.path.join(start_dir, entry.name), start_dir
            )
            
            # 跳过隐藏文件（除非搜索前缀以.开头）
            if not search_prefix.startswith('.') and entry.name.startswith('.'):
                continue
            
            # 检查文件过滤规则
            if file_discovery and file_discovery.should_ignore_file(
                entry_path_from_root, filter_options
            ):
                continue
            
            # 检查名称匹配
            if entry.name.lower().startswith(lower_search_prefix):
                suffix = '/' if entry.is_dir() else ''
                found_suggestions.append({
                    'label': entry_path_relative + suffix,
                    'value': escape_path(entry_path_relative + suffix)
                })
            
            # 递归搜索子目录
            if (entry.is_dir() and 
                entry.name != 'node_modules' and 
                not entry.name.startswith('.') and
                len(found_suggestions) < max_results):
                
                sub_suggestions = await find_files_recursively(
                    os.path.join(start_dir, entry.name),
                    search_prefix,
                    file_discovery,
                    filter_options,
                    entry_path_relative,
                    depth + 1,
                    max_depth,
                    max_results - len(found_suggestions)
                )
                found_suggestions.extend(sub_suggestions)
    
    except Exception:
        # 忽略权限错误等异常
        pass
    
    return found_suggestions[:max_results]
```

#### 3.3.2 Glob 搜索算法

```python
async def find_files_with_glob(
    search_prefix: str,
    file_discovery_service: FileDiscoveryService,
    filter_options: FilterOptions,
    search_dir: str,
    max_results: int = 50
) -> List[Suggestion]:
    """
    使用 glob 模式搜索文件
    
    Args:
        search_prefix: 搜索前缀
        file_discovery_service: 文件发现服务
        filter_options: 过滤选项
        search_dir: 搜索目录
        max_results: 最大结果数
    
    Returns:
        List[Suggestion]: 建议列表
    """
    glob_pattern = f"**/{search_prefix}*"
    
    files = await glob.glob(
        glob_pattern,
        cwd=search_dir,
        dot=search_prefix.startswith('.'),
        case_sensitive=False
    )
    
    suggestions = []
    for file in files[:max_results]:
        if file_discovery_service:
            if file_discovery_service.should_ignore_file(file, filter_options):
                continue
        
        absolute_path = os.path.abspath(os.path.join(search_dir, file))
        label = os.path.relpath(absolute_path, os.getcwd())
        
        suggestions.append({
            'label': label,
            'value': escape_path(label)
        })
    
    return suggestions
```

### 3.4 排序算法

```python
def sort_suggestions(suggestions: List[Suggestion]) -> List[Suggestion]:
    """
    对建议列表进行排序
    
    排序优先级:
    1. 路径深度（浅层优先）
    2. 目录类型（目录优先于文件）
    3. 文件名（不包括扩展名）
    4. 完整文件名
    
    Args:
        suggestions: 原始建议列表
    
    Returns:
        List[Suggestion]: 排序后的建议列表
    """
    def sort_key(suggestion: Suggestion) -> Tuple[int, bool, str, str]:
        label = suggestion['label']
        
        # 1. 计算路径深度
        depth = label.count('/')
        
        # 2. 判断是否为目录
        is_dir = label.endswith('/')
        dir_priority = 0 if is_dir else 1  # 目录优先
        
        # 3. 获取文件名（不含扩展名）
        basename = os.path.basename(label.rstrip('/'))
        name_without_ext = os.path.splitext(basename)[0]
        
        # 4. 完整标签名
        full_label = label
        
        return (depth, dir_priority, name_without_ext.lower(), full_label.lower())
    
    return sorted(suggestions, key=sort_key)
```

---

## 4. 文件过滤系统

### 4.1 过滤服务架构

```python
class FileDiscoveryService:
    """文件发现和过滤服务"""
    
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.git_ignore_filter = None
        self.gemini_ignore_filter = None
        
        # 初始化 Git 忽略过滤器
        if self._is_git_repository(self.project_root):
            self.git_ignore_filter = GitIgnoreParser(self.project_root)
            try:
                self.git_ignore_filter.load_git_repo_patterns()
            except FileNotFoundError:
                pass
        
        # 初始化 Gemini 忽略过滤器
        self.gemini_ignore_filter = GitIgnoreParser(self.project_root)
        try:
            self.gemini_ignore_filter.load_patterns('.geminiignore')
        except FileNotFoundError:
            pass
    
    def should_ignore_file(self, file_path: str, options: FilterOptions) -> bool:
        """
        检查文件是否应该被忽略
        
        Args:
            file_path: 文件路径
            options: 过滤选项
        
        Returns:
            bool: 是否应该忽略
        """
        if options.get('respect_git_ignore', True) and self._should_git_ignore_file(file_path):
            return True
        
        if options.get('respect_gemini_ignore', True) and self._should_gemini_ignore_file(file_path):
            return True
        
        return False
    
    def _should_git_ignore_file(self, file_path: str) -> bool:
        """检查文件是否被 git 忽略"""
        if self.git_ignore_filter:
            return self.git_ignore_filter.is_ignored(file_path)
        return False
    
    def _should_gemini_ignore_file(self, file_path: str) -> bool:
        """检查文件是否被 gemini 忽略"""
        if self.gemini_ignore_filter:
            return self.gemini_ignore_filter.is_ignored(file_path)
        return False
```

### 4.2 过滤配置

```python
@dataclass
class FilterOptions:
    """文件过滤配置选项"""
    respect_git_ignore: bool = True
    respect_gemini_ignore: bool = True

DEFAULT_FILTER_OPTIONS = FilterOptions(
    respect_git_ignore=True,
    respect_gemini_ignore=True
)
```

---

## 5. 路径处理工具

### 5.1 路径转义处理

```python
def escape_path(file_path: str) -> str:
    """
    转义文件路径中的空格
    
    Args:
        file_path: 原始文件路径
    
    Returns:
        str: 转义后的路径
    """
    result = ""
    for i, char in enumerate(file_path):
        # 只转义未被转义的空格
        if char == ' ' and (i == 0 or file_path[i-1] != '\\'):
            result += '\\ '
        else:
            result += char
    return result

def unescape_path(file_path: str) -> str:
    """
    反转义文件路径中的空格
    
    Args:
        file_path: 转义的文件路径
    
    Returns:
        str: 反转义后的路径
    """
    return file_path.replace('\\ ', ' ')
```

### 5.2 Unicode 文本处理

```python
def to_code_points(text: str) -> List[str]:
    """
    将字符串转换为 Unicode 代码点数组
    
    Args:
        text: 输入字符串
    
    Returns:
        List[str]: Unicode 代码点列表
    """
    return list(text)

def cp_len(text: str) -> int:
    """
    获取字符串的 Unicode 代码点长度
    
    Args:
        text: 输入字符串
    
    Returns:
        int: 代码点长度
    """
    return len(list(text))

def cp_slice(text: str, start: int, end: Optional[int] = None) -> str:
    """
    按 Unicode 代码点切片字符串
    
    Args:
        text: 输入字符串
        start: 起始位置
        end: 结束位置
    
    Returns:
        str: 切片后的字符串
    """
    code_points = list(text)
    return ''.join(code_points[start:end])
```

---

## 6. 用户交互系统

### 6.1 键盘导航

```python
class SuggestionNavigator:
    """建议列表导航器"""
    
    def __init__(self, max_visible: int = 8):
        self.suggestions: List[Suggestion] = []
        self.active_index: int = -1
        self.visible_start_index: int = 0
        self.max_visible = max_visible
    
    def navigate_up(self) -> None:
        """向上导航"""
        if not self.suggestions:
            return
        
        # 计算新的活动索引
        new_active_index = (
            len(self.suggestions) - 1 
            if self.active_index <= 0 
            else self.active_index - 1
        )
        
        # 调整滚动位置
        if new_active_index == len(self.suggestions) - 1:
            # 回绕到最后一项
            if len(self.suggestions) > self.max_visible:
                self.visible_start_index = max(0, len(self.suggestions) - self.max_visible)
        elif new_active_index < self.visible_start_index:
            # 向上滚动
            self.visible_start_index = new_active_index
        
        self.active_index = new_active_index
    
    def navigate_down(self) -> None:
        """向下导航"""
        if not self.suggestions:
            return
        
        # 计算新的活动索引
        new_active_index = (
            0 
            if self.active_index >= len(self.suggestions) - 1 
            else self.active_index + 1
        )
        
        # 调整滚动位置
        if new_active_index == 0:
            # 回绕到第一项
            self.visible_start_index = 0
        elif new_active_index >= self.visible_start_index + self.max_visible:
            # 向下滚动
            self.visible_start_index = new_active_index - self.max_visible + 1
        
        self.active_index = new_active_index
    
    def get_visible_suggestions(self) -> List[Suggestion]:
        """获取当前可见的建议"""
        end_index = min(
            self.visible_start_index + self.max_visible,
            len(self.suggestions)
        )
        return self.suggestions[self.visible_start_index:end_index]
```

### 6.2 自动完成处理

```python
def handle_autocomplete(
    buffer: TextBuffer,
    suggestions: List[Suggestion],
    selected_index: int
) -> None:
    """
    处理自动完成选择
    
    Args:
        buffer: 文本缓冲区
        suggestions: 建议列表
        selected_index: 选中的索引
    """
    if selected_index < 0 or selected_index >= len(suggestions):
        return
    
    query = buffer.get_text()
    suggestion = suggestions[selected_index]['value']
    
    if query.strip().startswith('/'):
        # 处理斜杠命令自动完成
        _handle_slash_command_autocomplete(buffer, query, suggestion)
    else:
        # 处理 @ 路径自动完成
        _handle_at_path_autocomplete(buffer, query, suggestion)

def _handle_at_path_autocomplete(buffer: TextBuffer, query: str, suggestion: str) -> None:
    """处理 @ 路径自动完成"""
    at_index = query.rfind('@')
    if at_index == -1:
        return
    
    path_part = query[at_index + 1:]
    last_slash_index = path_part.rfind('/')
    
    if last_slash_index == -1:
        autocomplete_start_index = at_index + 1
    else:
        autocomplete_start_index = at_index + 1 + last_slash_index + 1
    
    # 替换从自动完成位置到文本末尾的内容
    buffer.replace_range_by_offset(
        autocomplete_start_index,
        len(query),
        suggestion
    )
```

---

## 7. 配置系统

### 7.1 完成配置

```python
@dataclass
class CompletionConfig:
    """自动完成配置"""
    
    # 搜索配置
    enable_recursive_search: bool = True
    max_search_depth: int = 10
    max_results: int = 50
    debounce_delay_ms: int = 100
    
    # 显示配置
    max_visible_suggestions: int = 8
    suggestion_width: int = 60
    
    # 过滤配置
    respect_git_ignore: bool = True
    respect_gemini_ignore: bool = True
    
    # 性能配置
    search_timeout_ms: int = 5000
    
    # 用户体验配置
    show_loading_indicator: bool = True
    auto_select_first: bool = True

DEFAULT_COMPLETION_CONFIG = CompletionConfig()
```

### 7.2 工作区配置

```python
@dataclass
class WorkspaceConfig:
    """工作区配置"""
    directories: List[str]
    current_directory: str
    project_root: str
    
    def get_search_directories(self) -> List[str]:
        """获取搜索目录列表"""
        return self.directories if self.directories else [self.current_directory]
```

---

## 8. 性能优化策略

### 8.1 搜索优化

```python
class SearchOptimizer:
    """搜索性能优化器"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 30  # 缓存30秒
    
    async def optimized_search(
        self,
        search_prefix: str,
        directories: List[str],
        config: CompletionConfig
    ) -> List[Suggestion]:
        """
        优化的搜索实现
        
        策略:
        1. 缓存搜索结果
        2. 增量搜索
        3. 异步并发搜索
        4. 早期返回机制
        """
        cache_key = f"{search_prefix}:{':'.join(directories)}"
        
        # 检查缓存
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return self._filter_cached_results(cached_result, search_prefix)
        
        # 并发搜索多个目录
        search_tasks = []
        for directory in directories:
            task = self._search_directory(directory, search_prefix, config)
            search_tasks.append(task)
        
        # 等待所有搜索完成，但有超时机制
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*search_tasks),
                timeout=config.search_timeout_ms / 1000
            )
        except asyncio.TimeoutError:
            # 超时时返回已有结果
            results = []
            for task in search_tasks:
                if task.done():
                    results.append(task.result())
        
        # 合并和排序结果
        all_suggestions = []
        for result in results:
            all_suggestions.extend(result)
        
        sorted_suggestions = sort_suggestions(all_suggestions)
        limited_suggestions = sorted_suggestions[:config.max_results]
        
        # 更新缓存
        self.cache[cache_key] = (limited_suggestions, time.time())
        
        return limited_suggestions
```

### 8.2 防抖处理

```python
class Debouncer:
    """输入防抖处理器"""
    
    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms
        self.timer = None
    
    def debounce(self, func: Callable, *args, **kwargs) -> None:
        """
        防抖执行函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        """
        if self.timer:
            self.timer.cancel()
        
        self.timer = threading.Timer(
            self.delay_ms / 1000,
            lambda: func(*args, **kwargs)
        )
        self.timer.start()
    
    def cancel(self) -> None:
        """取消待执行的函数"""
        if self.timer:
            self.timer.cancel()
            self.timer = None
```

---

## 9. 错误处理机制

### 9.1 异常处理策略

```python
class CompletionError(Exception):
    """自动完成异常基类"""
    pass

class SearchTimeoutError(CompletionError):
    """搜索超时异常"""
    pass

class FileAccessError(CompletionError):
    """文件访问异常"""
    pass

async def safe_file_search(
    search_func: Callable,
    error_handler: Optional[Callable] = None
) -> List[Suggestion]:
    """
    安全的文件搜索包装器
    
    Args:
        search_func: 搜索函数
        error_handler: 错误处理函数
    
    Returns:
        List[Suggestion]: 搜索结果（错误时返回空列表）
    """
    try:
        return await search_func()
    except PermissionError:
        # 权限错误 - 静默忽略
        if error_handler:
            error_handler("Permission denied for some directories")
        return []
    except FileNotFoundError:
        # 文件不存在 - 静默忽略
        if error_handler:
            error_handler("Some directories do not exist")
        return []
    except asyncio.TimeoutError:
        # 搜索超时
        if error_handler:
            error_handler("Search timeout - showing partial results")
        return []
    except Exception as e:
        # 其他未知错误
        if error_handler:
            error_handler(f"Search error: {str(e)}")
        return []
```

### 9.2 降级策略

```python
class GracefulDegradation:
    """优雅降级处理"""
    
    @staticmethod
    def fallback_search(
        search_prefix: str,
        current_directory: str
    ) -> List[Suggestion]:
        """
        降级搜索实现（仅搜索当前目录）
        
        Args:
            search_prefix: 搜索前缀
            current_directory: 当前目录
        
        Returns:
            List[Suggestion]: 基础搜索结果
        """
        suggestions = []
        try:
            entries = os.listdir(current_directory)
            for entry in entries:
                if entry.startswith(search_prefix):
                    full_path = os.path.join(current_directory, entry)
                    is_dir = os.path.isdir(full_path)
                    suggestions.append({
                        'label': entry + ('/' if is_dir else ''),
                        'value': escape_path(entry + ('/' if is_dir else ''))
                    })
        except Exception:
            pass  # 静默失败
        
        return suggestions[:20]  # 限制结果数量
```

---

## 10. 测试用例规范

### 10.1 功能测试用例

```python
class TestFileRecommendation:
    """文件推荐功能测试用例"""
    
    def test_basic_at_detection(self):
        """测试基本 @ 检测功能"""
        test_cases = [
            ("@", 0, 1, True),           # 基本 @ 字符
            ("hello @", 0, 7, True),     # @ 前有文本
            ("@file", 0, 5, True),       # @ 后有文件名
            ("user\\@domain", 0, 11, False),  # 转义的 @
            ("no at symbol", 0, 12, False),   # 无 @ 字符
        ]
        
        for text, row, col, expected in test_cases:
            lines = text.split('\n')
            result = is_completion_active(text, row, col, lines)
            assert result == expected, f"Failed for: {text}"
    
    def test_path_parsing(self):
        """测试路径解析功能"""
        test_cases = [
            ("@file.txt", (".", "file.txt", "file.txt")),
            ("@src/", ("src/", "", "src/")),
            ("@src/main.py", ("src/", "main.py", "src/main.py")),
            ("@../config", ("../", "config", "../config")),
            ("hello @world", (".", "world", "world")),
        ]
        
        for input_text, expected in test_cases:
            base_dir, prefix, partial = parse_at_command_path(input_text)
            result = (base_dir, prefix, partial)
            assert result == expected, f"Failed for: {input_text}, got {result}, expected {expected}"
    
    def test_file_search(self):
        """测试文件搜索功能"""
        # 创建临时测试目录结构
        test_structure = {
            "config.json": "",
            "config.yaml": "",
            "src/": {
                "main.py": "",
                "utils.py": "",
                "tests/": {
                    "test_main.py": ""
                }
            },
            "docs/": {
                "README.md": ""
            }
        }
        
        with create_temp_directory(test_structure) as temp_dir:
            # 测试基本搜索
            suggestions = find_files_in_directory(temp_dir, "config")
            assert len(suggestions) == 2
            assert any(s['label'] == 'config.json' for s in suggestions)
            assert any(s['label'] == 'config.yaml' for s in suggestions)
            
            # 测试目录搜索
            suggestions = find_files_in_directory(temp_dir, "src")
            assert len(suggestions) >= 1
            assert any(s['label'] == 'src/' for s in suggestions)
    
    def test_sorting(self):
        """测试排序功能"""
        suggestions = [
            {'label': 'deep/nested/file.txt', 'value': 'deep/nested/file.txt'},
            {'label': 'config.json', 'value': 'config.json'},
            {'label': 'src/', 'value': 'src/'},
            {'label': 'src/main.py', 'value': 'src/main.py'},
            {'label': 'docs/', 'value': 'docs/'},
        ]
        
        sorted_suggestions = sort_suggestions(suggestions)
        
        # 检查排序结果
        labels = [s['label'] for s in sorted_suggestions]
        
        # 浅层文件应该排在前面
        shallow_files = [l for l in labels if '/' not in l.rstrip('/')]
        deep_files = [l for l in labels if l.count('/') > 1]
        
        # 目录应该优先于同级文件
        assert labels.index('src/') < labels.index('src/main.py')
    
    def test_keyboard_navigation(self):
        """测试键盘导航功能"""
        navigator = SuggestionNavigator(max_visible=3)
        suggestions = [
            {'label': 'file1.txt', 'value': 'file1.txt'},
            {'label': 'file2.txt', 'value': 'file2.txt'},
            {'label': 'file3.txt', 'value': 'file3.txt'},
            {'label': 'file4.txt', 'value': 'file4.txt'},
            {'label': 'file5.txt', 'value': 'file5.txt'},
        ]
        navigator.suggestions = suggestions
        navigator.active_index = 0
        
        # 测试向下导航
        navigator.navigate_down()
        assert navigator.active_index == 1
        
        # 测试向上导航
        navigator.navigate_up()
        assert navigator.active_index == 0
        
        # 测试回绕
        navigator.navigate_up()
        assert navigator.active_index == 4  # 应该回绕到最后一项

### 10.2 集成测试用例

```python
class TestIntegration:
    """集成测试用例"""
    
    def test_complete_workflow(self):
        """测试完整的推荐工作流程"""
        # 模拟用户输入序列
        inputs = [
            ("@", "应该显示所有顶级文件"),
            ("@con", "应该过滤显示以con开头的文件"),
            ("@config.", "应该显示config.开头的文件"),
            ("@src/", "应该显示src目录下的文件"),
        ]
        
        completion_engine = CompletionEngine()
        
        for input_text, description in inputs:
            suggestions = completion_engine.get_suggestions(input_text)
            assert len(suggestions) >= 0, f"Failed: {description}"
    
    def test_performance_benchmark(self):
        """性能基准测试"""
        import time
        
        # 创建大型目录结构
        large_structure = create_large_test_structure(1000)  # 1000个文件
        
        with create_temp_directory(large_structure) as temp_dir:
            start_time = time.time()
            
            completion_engine = CompletionEngine(
                search_directories=[temp_dir],
                config=CompletionConfig(max_results=50)
            )
            
            suggestions = completion_engine.get_suggestions("@test")
            
            end_time = time.time()
            search_time = end_time - start_time
            
            # 搜索应该在1秒内完成
            assert search_time < 1.0, f"Search took too long: {search_time}s"
            assert len(suggestions) > 0, "Should find some suggestions"

### 10.3 边界条件测试

```python
class TestEdgeCases:
    """边界条件测试"""
    
    def test_empty_input(self):
        """测试空输入"""
        assert not is_completion_active("", 0, 0, [""])
    
    def test_special_characters(self):
        """测试特殊字符"""
        test_cases = [
            "@file with spaces.txt",
            "@中文文件.txt",
            "@file-with-dashes.txt",
            "@file_with_underscores.txt",
            "@file.with.dots.txt",
        ]
        
        for case in test_cases:
            base_dir, prefix, partial = parse_at_command_path(case)
            assert prefix != "", f"Failed to parse: {case}"
    
    def test_large_file_count(self):
        """测试大量文件情况"""
        # 测试有10000个文件的目录
        suggestions = []
        for i in range(10000):
            suggestions.append({
                'label': f'file_{i:04d}.txt',
                'value': f'file_{i:04d}.txt'
            })
        
        # 排序应该仍然能够处理
        sorted_suggestions = sort_suggestions(suggestions)
        assert len(sorted_suggestions) == 10000
    
    def test_permission_errors(self):
        """测试权限错误处理"""
        # 模拟权限错误
        def mock_search_with_permission_error():
            raise PermissionError("Access denied")
        
        suggestions = safe_file_search(mock_search_with_permission_error)
        assert suggestions == []  # 应该返回空列表而不是抛出异常
```

---

## 11. Python 实现指南

### 11.1 依赖库推荐

```python
# requirements.txt
asyncio>=3.4.3          # 异步IO支持
pathlib>=1.0.1          # 现代路径处理
typing>=3.7.4           # 类型注解
dataclasses>=0.6        # 数据类支持
fnmatch>=1.0.2          # 文件名模式匹配
glob2>=0.7              # 扩展glob支持
gitignore-parser>=0.1.0 # .gitignore解析
rich>=13.0.0            # 终端UI库
prompt-toolkit>=3.0.0   # 高级输入处理
```

### 11.2 项目结构建议

```
file_recommendation/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── completion_engine.py      # 主要完成引擎
│   ├── file_discovery.py         # 文件发现服务
│   ├── suggestion.py             # 建议数据结构
│   └── config.py                 # 配置管理
├── utils/
│   ├── __init__.py
│   ├── path_utils.py             # 路径处理工具
│   ├── text_utils.py             # 文本处理工具
│   └── performance.py            # 性能优化工具
├── ui/
│   ├── __init__.py
│   ├── input_handler.py          # 输入处理
│   ├── suggestion_display.py     # 建议显示
│   └── keyboard_nav.py           # 键盘导航
├── filters/
│   ├── __init__.py
│   ├── git_filter.py             # Git忽略过滤
│   └── custom_filter.py          # 自定义过滤
└── tests/
    ├── __init__.py
    ├── test_completion.py         # 完成功能测试
    ├── test_performance.py        # 性能测试
    └── test_integration.py        # 集成测试
```

### 11.3 主要入口点

```python
# main.py - 主要API入口
from file_recommendation import FileRecommendationEngine

def main():
    """主要使用示例"""
    engine = FileRecommendationEngine(
        current_directory=os.getcwd(),
        config=CompletionConfig(
            enable_recursive_search=True,
            max_results=50,
            respect_git_ignore=True
        )
    )
    
    # 模拟用户输入
    user_input = "@src/main"
    
    if engine.should_show_suggestions(user_input):
        suggestions = engine.get_suggestions(user_input)
        
        # 显示建议
        for i, suggestion in enumerate(suggestions):
            print(f"{i+1}. {suggestion['label']}")
    
    return 0

if __name__ == "__main__":
    exit(main())
```

---

## 12. 实现优先级

### 12.1 MVP (最小可行产品)

**第一阶段 - 基础功能**:
1. 基本 @ 字符检测
2. 简单文件搜索（当前目录）
3. 基础建议显示
4. Tab 键自动完成

**预计工作量**: 1-2周

### 12.2 完整功能

**第二阶段 - 增强功能**:
1. 递归文件搜索
2. .gitignore 过滤支持
3. 键盘导航（上下箭头）
4. 路径转义处理

**预计工作量**: 2-3周

### 12.3 性能优化

**第三阶段 - 优化功能**:
1. 搜索结果缓存
2. 异步搜索
3. 防抖处理
4. 性能监控

**预计工作量**: 1-2周

---

## 13. 总结

本设计文档提供了 @ 文件推荐功能的完整技术规范，包括：

1. **核心算法**: 触发检测、路径解析、文件搜索和排序
2. **系统架构**: 模块化设计和清晰的组件分离
3. **用户交互**: 键盘导航和自动完成处理
4. **性能优化**: 缓存、异步处理和防抖机制
5. **错误处理**: 优雅降级和异常处理策略
6. **测试用例**: 功能测试、集成测试和边界条件测试

该文档为 Python 实现提供了详细的技术指导，确保功能的完整性和一致性。实现团队可以按照文档中的算法和架构进行开发，并使用提供的测试用例验证功能正确性。

---

**文档维护**: 本文档应随着功能演进而更新，确保技术规范的准确性和完整性。
