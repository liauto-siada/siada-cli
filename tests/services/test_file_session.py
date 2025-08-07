import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from siada.services.file_session import FileSession


class TestFileSession(unittest.TestCase):
    """Test cases for FileSession class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary directory for test sessions
        self.temp_dir = tempfile.mkdtemp()
        self.test_session_id = "test_session_123"
        self.test_sessions_dir = Path(self.temp_dir) / "test_sessions"
        
    def tearDown(self):
        """Clean up test fixtures"""
        # Clean up temporary directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_init_creates_session_directory(self):
        """Test that initialization creates the sessions directory"""
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        self.assertTrue(self.test_sessions_dir.exists())
        self.assertTrue(self.test_sessions_dir.is_dir())
        self.assertTrue(session.session_folder.exists())
        self.assertEqual(session.session_id, self.test_session_id)
        self.assertEqual(session.sessions_dir, self.test_sessions_dir)
        self.assertEqual(
            session.session_file, 
            self.test_sessions_dir / self.test_session_id / "api_history.json"
        )
    
    def test_init_with_existing_directory(self):
        """Test initialization with an already existing directory"""
        # Pre-create the directory
        self.test_sessions_dir.mkdir(parents=True, exist_ok=True)
        
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        self.assertTrue(self.test_sessions_dir.exists())
        self.assertEqual(session.session_id, self.test_session_id)
    
    def test_from_file_with_valid_session_file(self):
        """Test from_file class method with a valid session file"""
        # Create a test session file in new structure
        session_id = "existing_session_id"
        session_folder = self.test_sessions_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        session_file = session_folder / "api_history.json"
        
        test_data = {
            "session_id": session_id,
            "items": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
        }
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)
        
        # Create session from file
        session = FileSession.from_file(session_file)
        
        self.assertEqual(session.session_id, session_id)
        self.assertEqual(session.sessions_dir, self.test_sessions_dir)
        self.assertEqual(session.session_folder, session_folder)
        self.assertEqual(session.session_file, session_file)
    
    def test_from_file_with_missing_session_id(self):
        """Test from_file when session file doesn't contain session_id"""
        # Create a test session file without session_id in new structure
        session_id = "no_id_session"
        session_folder = self.test_sessions_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        session_file = session_folder / "api_history.json"
        
        test_data = {
            "items": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        with open(session_file, 'w') as f:
            json.dump(test_data, f)
        
        # Create session from file - should use folder name as session_id
        session = FileSession.from_file(session_file)
        
        self.assertEqual(session.session_id, session_id)
        self.assertEqual(session.sessions_dir, self.test_sessions_dir)
    
    def test_from_file_with_corrupted_file(self):
        """Test from_file with a corrupted JSON file"""
        # Create a corrupted session file in new structure
        session_id = "corrupted_session"
        session_folder = self.test_sessions_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        session_file = session_folder / "api_history.json"
        
        with open(session_file, 'w') as f:
            f.write("This is not valid JSON{]")
        
        # Create session from file - should use folder name as session_id
        session = FileSession.from_file(session_file)
        
        self.assertEqual(session.session_id, session_id)
        self.assertEqual(session.sessions_dir, self.test_sessions_dir)
    
    def test_from_file_with_nonexistent_file(self):
        """Test from_file with a non-existent file"""
        session_file = self.test_sessions_dir / "nonexistent.json"
        
        with self.assertRaises(FileNotFoundError) as context:
            FileSession.from_file(session_file)
        
        self.assertIn("Session file not found", str(context.exception))
    
    def test_from_file_with_wrong_filename(self):
        """Test from_file with wrong filename"""
        # Create a file with wrong name
        session_folder = self.test_sessions_dir / "test_session"
        session_folder.mkdir(parents=True, exist_ok=True)
        wrong_file = session_folder / "wrong_name.json"
        
        test_data = {
            "session_id": "test_session",
            "items": []
        }
        
        with open(wrong_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)
        
        with self.assertRaises(ValueError) as context:
            FileSession.from_file(wrong_file)
        
        self.assertIn("Expected api_history.json", str(context.exception))
    
    def test_read_session_data_empty(self):
        """Test reading session data when file doesn't exist"""
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        data = session._read_session_data()
        self.assertEqual(data, [])
    
    def test_read_session_data_with_content(self):
        """Test reading session data from existing file"""
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        # Create a test session file
        test_items = [
            {"role": "user", "content": "Test message 1"},
            {"role": "assistant", "content": "Test response 1"}
        ]
        test_data = {
            "session_id": self.test_session_id,
            "items": test_items
        }
        
        with open(session.session_file, 'w') as f:
            json.dump(test_data, f)
        
        data = session._read_session_data()
        self.assertEqual(data, test_items)
    
    def test_write_session_data(self):
        """Test writing session data to file"""
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        test_items = [
            {"role": "user", "content": "Write test 1"},
            {"role": "assistant", "content": "Write response 1"}
        ]
        
        session._write_session_data(test_items)
        
        # Verify file was created and contains correct data
        self.assertTrue(session.session_file.exists())
        
        with open(session.session_file, 'r') as f:
            data = json.load(f)
        
        self.assertEqual(data["session_id"], self.test_session_id)
        self.assertEqual(data["items"], test_items)
    
    def test_write_session_data_atomic_operation(self):
        """Test that write operation is atomic (uses temp file)"""
        session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
        
        test_items = [{"role": "user", "content": "Atomic test"}]
        
        # Mock the file operations to verify atomic write
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            # Mock Path operations
            with patch.object(Path, 'replace') as mock_replace:
                session._write_session_data(test_items)
                
                # Verify temp file was used
                mock_replace.assert_called_once()


class TestFileSessionAsync(unittest.TestCase):
    """Test cases for FileSession async methods"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_session_id = "test_async_session"
        self.test_sessions_dir = Path(self.temp_dir) / "async_sessions"
        self.session = FileSession(
            session_id=self.test_session_id,
            sessions_dir=self.test_sessions_dir
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_get_items_empty(self):
        """Test getting items from empty session"""
        async def run_test():
            items = await self.session.get_items()
            self.assertEqual(items, [])
        
        asyncio.run(run_test())
    
    def test_get_items_with_limit(self):
        """Test getting items with limit"""
        async def run_test():
            # Add test items
            test_items = [
                {"role": "user", "content": f"Message {i}"}
                for i in range(10)
            ]
            await self.session.add_items(test_items)
            
            # Get last 3 items
            items = await self.session.get_items(limit=3)
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0]["content"], "Message 7")
            self.assertEqual(items[-1]["content"], "Message 9")
            
            # Get all items when limit > total
            all_items = await self.session.get_items(limit=20)
            self.assertEqual(len(all_items), 10)
        
        asyncio.run(run_test())
    
    def test_add_items(self):
        """Test adding items to session"""
        async def run_test():
            test_items = [
                {"role": "user", "content": "First message"},
                {"role": "assistant", "content": "First response"}
            ]
            
            await self.session.add_items(test_items)
            
            # Verify items were added
            items = await self.session.get_items()
            self.assertEqual(items, test_items)
            
            # Add more items
            more_items = [
                {"role": "user", "content": "Second message"}
            ]
            await self.session.add_items(more_items)
            
            # Verify all items are present
            all_items = await self.session.get_items()
            self.assertEqual(len(all_items), 3)
            self.assertEqual(all_items[-1], more_items[0])
        
        asyncio.run(run_test())
    
    def test_add_items_empty_list(self):
        """Test adding empty list of items"""
        async def run_test():
            await self.session.add_items([])
            
            # Verify no items were added
            items = await self.session.get_items()
            self.assertEqual(items, [])
        
        asyncio.run(run_test())
    
    def test_pop_item(self):
        """Test popping item from session"""
        async def run_test():
            test_items = [
                {"role": "user", "content": "Message 1"},
                {"role": "assistant", "content": "Response 1"},
                {"role": "user", "content": "Message 2"}
            ]
            
            await self.session.add_items(test_items)
            
            # Pop last item
            popped = await self.session.pop_item()
            self.assertEqual(popped, test_items[-1])
            
            # Verify item was removed
            remaining = await self.session.get_items()
            self.assertEqual(len(remaining), 2)
            self.assertEqual(remaining, test_items[:-1])
            
            # Pop until empty
            await self.session.pop_item()
            await self.session.pop_item()
            
            # Pop from empty session
            result = await self.session.pop_item()
            self.assertIsNone(result)
        
        asyncio.run(run_test())
    
    def test_clear_session(self):
        """Test clearing session"""
        async def run_test():
            # Add items
            test_items = [
                {"role": "user", "content": "Test message"},
                {"role": "assistant", "content": "Test response"}
            ]
            await self.session.add_items(test_items)
            
            # Verify file exists
            self.assertTrue(self.session.session_file.exists())
            
            # Clear session
            await self.session.clear_session()
            
            # Verify file was deleted
            self.assertFalse(self.session.session_file.exists())
            
            # Verify session is empty
            items = await self.session.get_items()
            self.assertEqual(items, [])
        
        asyncio.run(run_test())
    
    def test_concurrent_operations(self):
        """Test thread safety with concurrent operations"""
        async def run_test():
            # Add initial items
            initial_items = [
                {"role": "user", "content": f"Initial {i}"}
                for i in range(5)
            ]
            await self.session.add_items(initial_items)
            
            # Define concurrent operations
            async def add_task(n):
                await self.session.add_items([
                    {"role": "user", "content": f"Concurrent {n}"}
                ])
            
            async def get_task():
                return await self.session.get_items()
            
            # Run concurrent operations
            tasks = []
            for i in range(10):
                tasks.append(add_task(i))
                if i % 2 == 0:
                    tasks.append(get_task())
            
            await asyncio.gather(*tasks)
            
            # Verify all items were added
            final_items = await self.session.get_items()
            self.assertEqual(len(final_items), 15)  # 5 initial + 10 concurrent
        
        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
