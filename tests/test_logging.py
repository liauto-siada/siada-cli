import unittest
import logging
import sys

from siada.foundation.logging import logger

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
