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
