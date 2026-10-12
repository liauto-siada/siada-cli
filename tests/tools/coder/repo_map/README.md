# RepoMap 测试用例

本目录包含 `siada/tools/coder/repo_map/` 的测试用例。

## 覆盖内容

### `test_io_and_token_counter.py`

- `IO` / `SilentIO`：`tool_output`、`tool_warning`、`tool_error` 的计数统计，以及 `read_text` 读取文件内容。
- `TokenCounterModel`：token 计数为正、空文本返回 0、重复计数命中缓存。
- `OptimizedTokenCounterModel`：以 `sampling_threshold=100` 构造，长文本的计数大于短文本。
- `create_silent_repo_map`：以测试目录（由 `__file__` 推导）为根、`map_tokens=512` 生成一次静默 repo map，并验证 token 计数与文件读取。
- 接口兼容性：上述类保留 `IO` / `TokenCounterModel` 对外使用的方法与属性。

### `test_complex_repo_map.py`

- `TestComplexRepoMap.test_complex_repo_map_generation`：在临时目录里现搭一个带跨文件引用的合成仓库（synthetic fixture：`app/`、`app/services/`、`app/utils/` 下的若干模块、类与方法），生成 repo map 并把结果写入另一个临时目录，只断言返回值是非空字符串。
- `TestComplexRepoMap.test_tag_extraction_from_complex_files`：对合成仓库中的文件提取标签，并在提取到定义标签时断言类名（`AgentRunner`）以 `def` 标签出现。

两个文件的 token 计数都在本地完成（`TokenCounterModel`：litellm 可用时用其计数器，否则按字符估算），不会调用模型推理接口。断言只检查结构与包含关系，不比对固定输出快照。

`test_complex_repo_map.py` 的合成仓库与输出目录都由 `tempfile` 创建、由 `addCleanup` 清理，不会改动仓库中的文件；依赖导入失败时整个用例会被跳过（`unittest.skipIf`），而不是报错。

## 运行测试

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"

# 两个文件一起跑
poetry -C "$REPO_ROOT" run python -m pytest \
  "$REPO_ROOT/tests/tools/coder/repo_map/test_io_and_token_counter.py" \
  "$REPO_ROOT/tests/tools/coder/repo_map/test_complex_repo_map.py" -q

# 只跑其中一个文件
poetry -C "$REPO_ROOT" run python -m pytest "$REPO_ROOT/tests/tools/coder/repo_map/test_io_and_token_counter.py" -q
poetry -C "$REPO_ROOT" run python -m pytest "$REPO_ROOT/tests/tools/coder/repo_map/test_complex_repo_map.py" -q

# 只跑单个用例
poetry -C "$REPO_ROOT" run python -m pytest \
  "$REPO_ROOT/tests/tools/coder/repo_map/test_complex_repo_map.py::TestComplexRepoMap::test_tag_extraction_from_complex_files" -q
```

Python 依赖由 Poetry 管理：`poetry -C "$REPO_ROOT" install --with dev`。`test_complex_repo_map.py` 也可以直接运行：`poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/tools/coder/repo_map/test_complex_repo_map.py"`。

> `demo_test_repo_map.py` 是手工演示脚本：`tests/pytest.ini` 限定 `python_files = test_*.py`，文件名不匹配，pytest 不会收集它。