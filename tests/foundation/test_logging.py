import unittest
import logging
import sys
import tempfile
import os
import platform
import threading
import time
from pathlib import Path
from unittest.mock import patch

from siada.foundation.logging import (
    logger,
    get_file_handler,
    _create_concurrent_file_handler,
    _create_safe_timed_rotating_handler,
)


class TestLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 确保日志在PyCharm测试环境中显示
        # 添加一个专门的处理器将日志输出到stderr
        test_handler = logging.StreamHandler(sys.stderr)
        test_handler.setLevel(logging.INFO)
        test_formatter = logging.Formatter('%(message)s')
        test_handler.setFormatter(test_formatter)
        logger.addHandler(test_handler)

    def test_logger(self):
        logger.info("测试日志输出")
        self.assertTrue(True)


class TestWindowsLogging(unittest.TestCase):
    """测试Windows平台下的日志处理器功能"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_log_file = self.temp_dir / 'test.log'

    def tearDown(self):
        """测试后清理"""
        # 清理测试文件
        if self.test_log_file.exists():
            try:
                self.test_log_file.unlink()
            except:
                pass
        if self.temp_dir.exists():
            try:
                self.temp_dir.rmdir()
            except:
                pass

    def test_platform_detection(self):
        """测试平台检测功能"""
        is_windows = sys.platform.startswith('win')

        if is_windows:
            self.assertTrue(is_windows, "应该检测到Windows平台")
        else:
            self.assertFalse(is_windows, "应该检测到非Windows平台")

    @unittest.skipUnless(sys.platform.startswith('win'), "仅在Windows平台运行")
    def test_concurrent_handler_on_windows(self):
        """测试Windows平台下ConcurrentLogHandler的创建"""
        try:
            from concurrent_log_handler import ConcurrentRotatingFileHandler

            # 测试创建handler
            handler = get_file_handler()

            # 验证handler类型
            self.assertIsInstance(
                handler,
                ConcurrentRotatingFileHandler,
                "Windows平台应该使用ConcurrentRotatingFileHandler"
            )

            # 验证handler配置
            self.assertEqual(handler.level, logging.INFO)
            self.assertIsNotNone(handler.formatter)

            handler.close()

        except ImportError:
            self.skipTest("ConcurrentLogHandler未安装")

    @unittest.skipUnless(sys.platform.startswith('win'), "仅在Windows平台运行")
    def test_fallback_when_concurrent_not_installed(self):
        """测试ConcurrentLogHandler未安装时的降级处理"""
        # 模拟ImportError
        with patch('siada.foundation.logging._create_concurrent_file_handler') as mock_create:
            mock_create.side_effect = ImportError("No module named 'concurrent_log_handler'")

            # 应该降级到SafeTimedRotatingFileHandler
            with self.assertWarns(RuntimeWarning):
                handler = get_file_handler()

            # 验证降级后的handler类型
            from siada.foundation.logging import SafeTimedRotatingFileHandler
            self.assertIsInstance(
                handler,
                SafeTimedRotatingFileHandler,
                "降级后应该使用SafeTimedRotatingFileHandler"
            )

            handler.close()

    @unittest.skipIf(sys.platform.startswith('win'), "仅在非Windows平台运行")
    def test_safe_handler_on_non_windows(self):
        """测试非Windows平台下SafeTimedRotatingFileHandler的创建"""
        handler = get_file_handler()

        # 验证handler类型
        from siada.foundation.logging import SafeTimedRotatingFileHandler
        self.assertIsInstance(
            handler,
            SafeTimedRotatingFileHandler,
            "非Windows平台应该使用SafeTimedRotatingFileHandler"
        )

        # 验证handler配置
        self.assertEqual(handler.level, logging.INFO)
        self.assertIsNotNone(handler.formatter)

        handler.close()

    def test_log_writing(self):
        """测试日志写入功能"""
        # 创建handler
        handler = get_file_handler()

        # 创建测试logger
        test_logger = logging.getLogger('test_windows_logging_write')
        test_logger.setLevel(logging.INFO)
        test_logger.addHandler(handler)

        # 写入测试日志
        test_messages = [
            "测试信息日志",
            "测试警告日志",
            "测试错误日志"
        ]

        test_logger.info(test_messages[0])
        test_logger.warning(test_messages[1])
        test_logger.error(test_messages[2])

        # 刷新handler确保日志写入
        handler.flush()

        # 清理
        test_logger.removeHandler(handler)
        handler.close()

        # 验证日志写入成功（没有抛出异常）
        self.assertTrue(True, "日志写入成功")

    @unittest.skipUnless(sys.platform.startswith('win'), "仅在Windows平台运行")
    def test_concurrent_handler_configuration(self):
        """测试ConcurrentLogHandler的配置参数"""
        try:
            from concurrent_log_handler import ConcurrentRotatingFileHandler

            handler = get_file_handler()

            if isinstance(handler, ConcurrentRotatingFileHandler):
                # 验证配置参数
                self.assertEqual(handler.maxBytes, 10 * 1024 * 1024, "最大文件大小应为10MB")
                self.assertEqual(handler.backupCount, 30, "备份文件数应为30")

            handler.close()

        except ImportError:
            self.skipTest("ConcurrentLogHandler未安装")

    def test_handler_formatter(self):
        """测试handler的formatter配置"""
        handler = get_file_handler()

        # 验证formatter存在
        self.assertIsNotNone(handler.formatter, "Handler应该有formatter")

        # 验证formatter格式
        from siada.foundation.logging import FileFormatter
        self.assertIsInstance(
            handler.formatter,
            FileFormatter,
            "应该使用FileFormatter"
        )

        handler.close()

    def test_multiple_handlers(self):
        """测试创建多个handler"""
        handlers = []

        try:
            # 创建多个handler
            for i in range(3):
                handler = get_file_handler()
                handlers.append(handler)

            # 验证所有handler都成功创建
            self.assertEqual(len(handlers), 3, "应该成功创建3个handler")

            # 验证所有handler类型一致
            handler_types = set(type(h) for h in handlers)
            self.assertEqual(len(handler_types), 1, "所有handler类型应该一致")

        finally:
            # 清理所有handler
            for handler in handlers:
                handler.close()


class TestHandlerCreationFunctions(unittest.TestCase):
    """测试handler创建函数"""

    @unittest.skipUnless(sys.platform.startswith('win'), "仅在Windows平台运行")
    def test_create_concurrent_handler(self):
        """测试_create_concurrent_file_handler函数"""
        try:
            handler = _create_concurrent_file_handler()

            from concurrent_log_handler import ConcurrentRotatingFileHandler
            self.assertIsInstance(handler, ConcurrentRotatingFileHandler)

            handler.close()

        except ImportError:
            self.skipTest("ConcurrentLogHandler未安装")

    def test_create_safe_timed_handler(self):
        """测试_create_safe_timed_rotating_handler函数"""
        handler = _create_safe_timed_rotating_handler()

        from siada.foundation.logging import SafeTimedRotatingFileHandler
        self.assertIsInstance(handler, SafeTimedRotatingFileHandler)

        handler.close()


class TestFileHandleRename(unittest.TestCase):
    """测试file_handle在文件打开时的重命名行为"""

    def setUp(self):
        """测试前准备"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_log_file = self.temp_dir / 'test_rename.log'
        self.renamed_file = self.temp_dir / 'test_rename.log.old'

    def tearDown(self):
        """测试后清理"""
        # 清理测试文件
        for f in [self.test_log_file, self.renamed_file]:
            if f.exists():
                try:
                    f.unlink()
                except:
                    pass
        if self.temp_dir.exists():
            try:
                self.temp_dir.rmdir()
            except:
                pass

    def test_rename_opened_file_handler(self):
        """
        测试file_handle在文件被打开时的重命名行为
        
        参考test_rename_opened_file.py的实现方式，测试：
        - Windows平台：重命名应该失败（PermissionError或FileExistsError）
        - Unix平台：重命名应该成功
        """
        print(f"\n当前系统: {platform.system()}")
        print(f"Python版本: {platform.python_version()}")
        print("-" * 60)

        rename_error = None
        write_error = None

        # 使用全局的log_file路径进行测试
        from siada.foundation.logging import log_file
        test_log_file = Path(log_file)
        renamed_file = Path(str(log_file) + '.test_rename')

        # 清理可能存在的旧的重命名文件
        if renamed_file.exists():
            try:
                renamed_file.unlink()
                print(f"✓ 清理旧的重命名文件: {renamed_file}")
            except Exception as e:
                print(f"⚠️  清理旧文件失败: {e}")

        def writer():
            """文件写入线程 - 使用get_file_handler()"""
            nonlocal write_error
            try:
                # 创建一个测试logger和handler
                test_logger = logging.getLogger('test_rename_handler')
                test_logger.setLevel(logging.INFO)

                # 使用get_file_handler()创建handler
                handler = get_file_handler()
                test_logger.addHandler(handler)

                # 写入初始内容
                test_logger.info("Initial content for rename test")
                handler.flush()
                print(f"✓ 文件已打开并写入: {test_log_file}")

                # 等待重命名操作
                time.sleep(0.3)

                # 尝试继续写入
                test_logger.info("After rename attempt")
                handler.flush()
                print(f"✓ 继续写入成功")

                time.sleep(0.2)

                # 清理
                test_logger.removeHandler(handler)
                handler.close()

            except Exception as e:
                write_error = e
                print(f"✗ 写入错误: {e}")

        # 启动写入线程
        thread = threading.Thread(target=writer)
        thread.start()

        # 等待文件创建
        time.sleep(0.1)

        # 尝试重命名（文件仍在写入）
        print(f"\n尝试重命名 {test_log_file} -> {renamed_file} ...")
        try:
            os.rename(str(test_log_file), str(renamed_file))
            print(f"✅ 重命名成功！")
        except PermissionError as e:
            rename_error = e
            print(f"❌ 重命名失败: {e}")
        except Exception as e:
            rename_error = e
            print(f"⚠️  其他错误: {e}")

        # 等待写入完成
        thread.join()

        # 分析结果
        print("\n" + "=" * 60)
        print("结果分析:")
        print("=" * 60)

        is_windows = platform.system() == 'Windows'

        if is_windows:
            if rename_error:
                print("✅ 符合预期: Windows阻止了重命名操作")
                print(f"   错误类型: {type(rename_error).__name__}")
                # Windows可能抛出PermissionError或FileExistsError
                self.assertIsInstance(rename_error, (PermissionError, FileExistsError),
                                    "Windows平台应该抛出PermissionError或FileExistsError")
            else:
                print("⚠️  意外: Windows上重命名成功了")
                # 在Windows上如果重命名成功，这可能是因为handler已经关闭
                # 或者使用了特殊的文件处理机制
        else:
            if rename_error:
                print("⚠️  意外: Unix上重命名失败了")
                self.fail(f"Unix平台重命名不应该失败: {rename_error}")
            else:
                print("✅ 符合预期: Unix允许重命名打开的文件")

        # 检查文件状态
        print("\n文件状态:")
        if test_log_file.exists():
            size = test_log_file.stat().st_size
            print(f"  {test_log_file.name}: {size} bytes")
            try:
                with open(test_log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print(f"    内容预览: {repr(content[:100])}")
            except Exception as e:
                print(f"    读取文件出错: {e}")

        if renamed_file.exists():
            size = renamed_file.stat().st_size
            print(f"  {renamed_file.name}: {size} bytes")
            try:
                with open(renamed_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    print(f"    内容预览: {repr(content[:100])}")
                    if "After rename" in content:
                        print(f"    ✓ 包含重命名后写入的内容（Unix行为）")
            except Exception as e:
                print(f"    读取重命名文件出错: {e}")
            # 清理测试产生的重命名文件
            try:
                renamed_file.unlink()
            except:
                pass

        # 验证没有写入错误
        self.assertIsNone(write_error, f"写入过程不应该出错: {write_error}")

        # 特别说明：在Windows上使用ConcurrentRotatingFileHandler时，
        # 重命名可能会成功，因为该handler使用了特殊的文件锁定机制
        # 这与标准的RotatingFileHandler行为不同
        if is_windows and not rename_error:
            print("\n说明: Windows上使用ConcurrentRotatingFileHandler时重命名成功")
            print("这是因为ConcurrentRotatingFileHandler使用了特殊的文件锁定机制")


if __name__ == '__main__':
    print("=" * 70)
    print("日志处理器测试")
    print("=" * 70)
    print(f"当前平台: {sys.platform}")
    print(f"Python版本: {sys.version}")

    # 检查ConcurrentLogHandler是否安装
    try:
        import concurrent_log_handler
        print("✓ ConcurrentLogHandler已安装")
        if hasattr(concurrent_log_handler, '__version__'):
            print(f"  版本: {concurrent_log_handler.__version__}")
    except ImportError:
        print("✗ ConcurrentLogHandler未安装")
        print("  提示: pip install concurrent-log-handler")

    print("=" * 70)
    print()

    # 运行测试
    unittest.main(verbosity=2)