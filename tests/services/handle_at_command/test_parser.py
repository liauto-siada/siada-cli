"""
Tests for AtCommandParser
"""

import unittest
from siada.services.handle_at_command.parser import AtCommandParser
from siada.services.handle_at_command.models import AtCommandPart


class TestAtCommandParser(unittest.TestCase):
    """Test cases for AtCommandParser"""
    
    def setUp(self):
        self.parser = AtCommandParser()
    
    def test_parse_single_at_command(self):
        """Test parsing a single @ command"""
        result = self.parser.parse_all_at_commands("@file.txt")
        expected = [AtCommandPart('atPath', '@file.txt')]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, expected[0].type)
        self.assertEqual(result[0].content, expected[0].content)
    
    def test_parse_mixed_content(self):
        """Test parsing mixed text and @ commands"""
        result = self.parser.parse_all_at_commands("Check @file1.txt and @file2.txt")
        expected = [
            AtCommandPart('text', 'Check '),
            AtCommandPart('atPath', '@file1.txt'),
            AtCommandPart('text', ' and '),
            AtCommandPart('atPath', '@file2.txt')
        ]
        self.assertEqual(len(result), 4)
        for i, part in enumerate(result):
            self.assertEqual(part.type, expected[i].type)
            self.assertEqual(part.content, expected[i].content)
    
    def test_parse_escaped_spaces(self):
        """Test parsing @ commands with escaped spaces"""
        result = self.parser.parse_all_at_commands("@my\\ file.txt")
        expected = [AtCommandPart('atPath', '@my file.txt')]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, expected[0].type)
        self.assertEqual(result[0].content, expected[0].content)
    
    def test_parse_lone_at_symbol(self):
        """Test parsing lone @ symbol"""
        result = self.parser.parse_all_at_commands("Just @ symbol")
        # The parser correctly splits this into 3 text parts
        expected = [
            AtCommandPart('text', 'Just '),
            AtCommandPart('text', '@'),
            AtCommandPart('text', ' symbol')
        ]
        self.assertEqual(len(result), 3)
        for i, part in enumerate(result):
            self.assertEqual(part.type, expected[i].type)
            self.assertEqual(part.content, expected[i].content)

    def test_parse_all_at_commands_exclude_invalids_diff_hunk(self):
        """@@ -45,13 +45,24 这种 diff hunk 不应该被识别为 atPath"""
        text = "@@ -45,13 +45,24 some diff context"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        # 整体应当视为普通文本
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_hex_ids(self):
        """日志里的十六进制 id / 指针，形如 @2f2e49 或 @0x3db83141，也应被视为普通文本"""
        text = "S.SurfaceTexture@2f2e49 mNative0bject=-5476106802210068736)/@0x3db83141"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_placeholder(self):
        """@{其它描述} 这一类占位符式写法也不应被识别为路径"""
        text = "请参考 @{其它描述} 这里的说明"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_unix_socket(self):
        """@/dev/socket/... 这类 Unix 域套接字路径也应当视为普通文本"""
        text = "连接 @/dev/socket/car_property_service/cps_server 失败"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_audio_bus(self):
        """@:BUS00_MEDIA 这类音频总线标签也不应被识别为路径"""
        text = "当前音频总线为 @:BUS00_MEDIA"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_resolution_tag(self):
        """@600w_800h_1c 这种分辨率标签也属于无效地址"""
        text = "使用分辨率配置 @600w_800h_1c 进行渲染"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)

    def test_parse_all_at_commands_exclude_invalids_systemd_service(self):
        """@configfs.service 这类 systemd service 也应被视为文本"""
        text = "加载单元 @configfs.service 失败"
        result = self.parser.parse_all_at_commands_exclude_invalids(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, 'text')
        self.assertEqual(result[0].content, text)
    
    def test_parse_empty_query(self):
        """Test parsing empty query"""
        result = self.parser.parse_all_at_commands("")
        self.assertEqual(len(result), 0)
    
    def test_parse_no_at_commands(self):
        """Test parsing query with no @ commands"""
        result = self.parser.parse_all_at_commands("This is just text")
        expected = [AtCommandPart('text', 'This is just text')]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, expected[0].type)
        self.assertEqual(result[0].content, expected[0].content)
    
    def test_validate_at_path(self):
        """Test @ path validation"""
        # Valid paths
        self.assertTrue(self.parser.validate_at_path("@file.txt"))
        self.assertTrue(self.parser.validate_at_path("@path/to/file.py"))
        self.assertTrue(self.parser.validate_at_path("@"))
        
        # Invalid paths
        self.assertFalse(self.parser.validate_at_path(""))
        self.assertFalse(self.parser.validate_at_path("file.txt"))  # No @
        self.assertFalse(self.parser.validate_at_path("@file<.txt"))  # Invalid char
        self.assertFalse(self.parser.validate_at_path("@file>.txt"))  # Invalid char
    
    def test_extract_file_content_info(self):
        """Test extracting file content information"""
        content = "--- test.py ---\n\nprint('hello')\n\n"
        file_path, extracted_content = self.parser.extract_file_content_info(content)
        self.assertEqual(file_path, "test.py")
        self.assertEqual(extracted_content, "print('hello')")
        
        # Test non-matching content
        non_matching = "Just some text"
        file_path, extracted_content = self.parser.extract_file_content_info(non_matching)
        self.assertIsNone(file_path)
        self.assertEqual(extracted_content, non_matching)


if __name__ == '__main__':
    unittest.main()
