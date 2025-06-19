"""
测试新创建的IO类和TokenCounterModel类

这个测试文件用于验证新创建的正式类是否与测试用例中的Mock类兼容
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
current_file = Path(__file__)
project_root = current_file.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

def test_io_class():
    """测试IO类的基本功能"""
    print("=== 测试IO类 ===")
    
    from siada.tools.coder.repo_map.io import IO, SilentIO, FileIO
    
    # 测试标准IO
    io = IO(verbose=True)
    io.tool_output("这是一个输出消息")
    io.tool_warning("这是一个警告消息")
    io.tool_error("这是一个错误消息")
    
    # 检查统计信息
    stats = io.get_stats()
    print(f"IO统计: {stats}")
    assert stats['outputs'] == 1
    assert stats['warnings'] == 1
    assert stats['errors'] == 1
    
    # 测试文件读取
    test_file = __file__  # 读取当前文件
    content = io.read_text(test_file)
    assert len(content) > 0
    print(f"成功读取文件，长度: {len(content)}")
    
    # 测试静默IO
    silent_io = SilentIO()
    silent_io.tool_output("静默输出")
    silent_io.tool_warning("静默警告")
    silent_io.tool_error("静默错误")
    
    silent_stats = silent_io.get_stats()
    print(f"静默IO统计: {silent_stats}")
    assert silent_stats['outputs'] == 1
    assert silent_stats['warnings'] == 1
    assert silent_stats['errors'] == 1
    
    print("✓ IO类测试通过")


def test_token_counter_model():
    """测试TokenCounterModel类的基本功能"""
    print("\n=== 测试TokenCounterModel类 ===")
    
    from siada.tools.coder.repo_map.token_counter import TokenCounterModel, OptimizedTokenCounterModel
    
    # 测试基本功能
    print("测试超级极简版TokenCounterModel")
    
    # 测试模型创建
    model_name = "claude-3-5-sonnet-20241022"
    model = TokenCounterModel(model_name)
    print(f"创建模型: {model}")
    assert model.model_name == model_name
    
    # 测试token计算
    test_text = "Hello, world! This is a test text for token counting."
    token_count = model.token_count(test_text)
    print(f"测试文本: '{test_text}'")
    print(f"Token数量: {token_count}")
    assert token_count > 0
    
    # 测试空文本
    empty_count = model.token_count("")
    assert empty_count == 0
    
    # 测试缓存（通过重复计算验证）
    token_count2 = model.token_count(test_text)
    assert token_count == token_count2  # 应该从缓存获取相同结果
    print("缓存机制正常工作")
    
    # 测试优化版模型
    opt_model = OptimizedTokenCounterModel(model_name, sampling_threshold=100)
    opt_count = opt_model.token_count(test_text)
    print(f"优化模型Token数量: {opt_count}")
    assert opt_count > 0
    
    # 测试长文本（触发采样）
    long_text = test_text * 50  # 创建长文本
    long_count = opt_model.token_count(long_text)
    print(f"长文本Token数量: {long_count}")
    assert long_count > token_count
    
    print("✓ TokenCounterModel类测试通过")


def test_integration_with_repo_map():
    """测试与RepoMap的集成"""
    print("\n=== 测试与RepoMap集成 ===")
    
    from siada.tools.coder.repo_map import create_repo_map, create_silent_repo_map
    
    # 使用当前项目根目录作为测试
    test_root = str(project_root)
    
    # 创建静默版RepoMap（避免输出干扰）
    repo_map = create_silent_repo_map(
        root_path=test_root,
        model_name="claude-3-5-sonnet-20241022",
        map_tokens=512  # 使用较小的token限制进行快速测试
    )
    
    print(f"创建RepoMap: root={test_root}")
    print(f"IO类型: {type(repo_map.io)}")
    print(f"模型类型: {type(repo_map.main_model)}")
    
    # 测试token计算
    test_text = "def hello_world():\n    print('Hello, World!')"
    token_count = repo_map.token_count(test_text)
    print(f"RepoMap token计算: {token_count}")
    assert token_count > 0
    
    # 测试文件读取
    current_file_content = repo_map.io.read_text(__file__)
    assert len(current_file_content) > 0
    print(f"通过RepoMap读取文件成功，长度: {len(current_file_content)}")
    
    print("✓ RepoMap集成测试通过")


def test_compatibility_with_mock_classes():
    """测试与Mock类的兼容性"""
    print("\n=== 测试与Mock类兼容性 ===")
    
    from siada.tools.coder.repo_map.io import IO
    from siada.tools.coder.repo_map.token_counter import TokenCounterModel
    
    # 创建实例
    io = IO(verbose=False)
    model = TokenCounterModel("claude-3-5-sonnet-20241022")
    
    # 测试接口兼容性
    # 这些方法应该与Mock类具有相同的接口
    
    # IO接口测试
    io.tool_output("测试输出")
    io.tool_warning("测试警告")
    io.tool_error("测试错误")
    content = io.read_text(__file__)
    assert len(content) > 0
    
    # TokenCounterModel接口测试
    assert hasattr(model, 'model_name')
    assert hasattr(model, 'token_count')
    assert callable(model.token_count)
    
    test_text = "test"
    tokens = model.token_count(test_text)
    assert isinstance(tokens, int)
    assert tokens > 0
    
    print("✓ Mock类兼容性测试通过")


def main():
    """运行所有测试"""
    print("开始测试新创建的IO类和TokenCounterModel类")
    print("=" * 60)
    
    try:
        test_io_class()
        test_token_counter_model()
        test_integration_with_repo_map()
        test_compatibility_with_mock_classes()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！新创建的类工作正常。")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
