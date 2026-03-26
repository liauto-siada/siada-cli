"""
Tests for CronTaskStorage - focused on disk storage operations
"""
import tempfile
from pathlib import Path
import json
import pytest

from siada.agent_hub.proactive.cron_task_storage import CronTaskStorage
from siada.agent_hub.proactive.models import CronTask


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "cron_tasks.json"
        storage = CronTaskStorage(str(storage_path))
        yield storage


class TestCronTaskStorageDiskOperations:
    """Test actual disk read/write operations"""
    
    def test_save_and_load_single_task(self, temp_storage):
        """Test saving task to disk and loading it back"""
        task = CronTask.create(
            name="Test task",
            cron_expr="0 9 * * *",
            instruction="Test instruction"
        )
        
        # Save task
        assert temp_storage.add(task) is True
        
        # Verify file was created on disk
        assert temp_storage.storage_path.exists()
        
        # Load tasks and verify
        loaded_tasks = temp_storage.load_all()
        assert len(loaded_tasks) == 1
        assert loaded_tasks[0].id == task.id
        assert loaded_tasks[0].name == task.name
        assert loaded_tasks[0].cron_expr == task.cron_expr
    
    def test_save_multiple_tasks_persists_to_disk(self, temp_storage):
        """Test that multiple tasks are correctly persisted to disk"""
        tasks = [
            CronTask.create(name=f"Task {i}", cron_expr="0 9 * * *", instruction="Test")
            for i in range(3)
        ]
        
        # Add all tasks
        for task in tasks:
            temp_storage.add(task)
        
        # Create new storage instance to force reload from disk
        new_storage = CronTaskStorage(str(temp_storage.storage_path))
        loaded_tasks = new_storage.load_all()
        
        assert len(loaded_tasks) == 3
        loaded_ids = {t.id for t in loaded_tasks}
        original_ids = {t.id for t in tasks}
        assert loaded_ids == original_ids
    
    def test_update_persists_to_disk(self, temp_storage):
        """Test that updates are written to disk"""
        task = CronTask.create(name="Original", cron_expr="0 9 * * *", instruction="Test")
        temp_storage.add(task)
        
        # Update task
        temp_storage.update(task.id, name="Updated", enabled=False)
        
        # Reload from disk
        new_storage = CronTaskStorage(str(temp_storage.storage_path))
        loaded_tasks = new_storage.load_all()
        
        assert len(loaded_tasks) == 1
        assert loaded_tasks[0].name == "Updated"
        assert loaded_tasks[0].enabled is False
    
    def test_delete_persists_to_disk(self, temp_storage):
        """Test that deletion is written to disk"""
        task1 = CronTask.create(name="Task 1", cron_expr="0 9 * * *", instruction="Test")
        task2 = CronTask.create(name="Task 2", cron_expr="0 10 * * *", instruction="Test")
        
        temp_storage.add(task1)
        temp_storage.add(task2)
        
        # Delete one task
        temp_storage.delete(task1.id)
        
        # Reload from disk
        new_storage = CronTaskStorage(str(temp_storage.storage_path))
        loaded_tasks = new_storage.load_all()
        
        assert len(loaded_tasks) == 1
        assert loaded_tasks[0].id == task2.id
    
    def test_storage_file_format(self, temp_storage):
        """Test that storage file has correct JSON format"""
        task = CronTask.create(name="Test", cron_expr="0 9 * * *", instruction="Test")
        temp_storage.add(task)
        
        # Read raw file content
        with open(temp_storage.storage_path, 'r') as f:
            data = json.load(f)
        
        # Verify structure
        assert "version" in data
        assert "last_updated" in data
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == task.id


class TestCronTaskStorageCRUD:
    """Test CRUD operations with actual disk persistence"""
    
    def test_add_duplicate_id_fails(self, temp_storage):
        """Test that adding task with duplicate ID fails"""
        task = CronTask.create(name="Test", cron_expr="0 9 * * *", instruction="Test")
        
        assert temp_storage.add(task) is True
        
        # Try to add same task again
        assert temp_storage.add(task) is False
        
        # Verify only one task exists
        assert len(temp_storage.load_all()) == 1
    
    def test_update_nonexistent_task_fails(self, temp_storage):
        """Test that updating non-existent task fails"""
        result = temp_storage.update("nonexistent-id", name="New name")
        assert result is False
    
    def test_delete_nonexistent_task_fails(self, temp_storage):
        """Test that deleting non-existent task fails"""
        result = temp_storage.delete("nonexistent-id")
        assert result is False
    
    def test_get_returns_correct_task(self, temp_storage):
        """Test retrieving specific task by ID"""
        task1 = CronTask.create(name="Task 1", cron_expr="0 9 * * *", instruction="Test")
        task2 = CronTask.create(name="Task 2", cron_expr="0 10 * * *", instruction="Test")
        
        temp_storage.add(task1)
        temp_storage.add(task2)
        
        retrieved = temp_storage.get(task1.id)
        assert retrieved is not None
        assert retrieved.id == task1.id
        assert retrieved.name == "Task 1"
    
    def test_get_enabled_filters_correctly(self, temp_storage):
        """Test that get_enabled returns only enabled tasks"""
        task1 = CronTask.create(name="Enabled", cron_expr="0 9 * * *", instruction="Test", enabled=True)
        task2 = CronTask.create(name="Disabled", cron_expr="0 10 * * *", instruction="Test", enabled=False)
        
        temp_storage.add(task1)
        temp_storage.add(task2)
        
        enabled_tasks = temp_storage.get_enabled()
        assert len(enabled_tasks) == 1
        assert enabled_tasks[0].id == task1.id
    
    def test_clear_removes_all_tasks(self, temp_storage):
        """Test that clear removes all tasks from disk"""
        for i in range(3):
            task = CronTask.create(name=f"Task {i}", cron_expr="0 9 * * *", instruction="Test")
            temp_storage.add(task)
        
        # Clear storage
        temp_storage.clear()
        
        # Verify file still exists but is empty
        assert temp_storage.storage_path.exists()
        assert len(temp_storage.load_all()) == 0
        
        # Reload from disk to verify persistence
        new_storage = CronTaskStorage(str(temp_storage.storage_path))
        assert len(new_storage.load_all()) == 0


class TestCronTaskStorageAtomicity:
    """Test atomic write operations"""
    
    def test_atomic_write_no_partial_writes(self, temp_storage):
        """Test that writes are atomic - no partial data on disk"""
        # This is hard to test directly, but we can verify the mechanism
        task = CronTask.create(name="Test", cron_expr="0 9 * * *", instruction="Test")
        temp_storage.add(task)
        
        # File should exist and be valid JSON
        with open(temp_storage.storage_path, 'r') as f:
            data = json.load(f)
        
        # Should not have any temporary files left
        temp_files = list(temp_storage.storage_path.parent.glob(".cron_tasks_*.tmp"))
        assert len(temp_files) == 0
    
    def test_load_empty_file_returns_empty_list(self, temp_storage):
        """Test loading when no file exists returns empty list"""
        tasks = temp_storage.load_all()
        assert tasks == []
        assert not temp_storage.storage_path.exists()
    
    def test_load_corrupted_file_returns_empty_list(self, temp_storage):
        """Test that corrupted JSON file returns empty list"""
        # Create a corrupted file
        temp_storage.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage.storage_path, 'w') as f:
            f.write("{ invalid json }")
        
        tasks = temp_storage.load_all()
        assert tasks == []


class TestCronTaskStorageHelpers:
    """Test helper methods"""
    
    def test_count_returns_correct_number(self, temp_storage):
        """Test count method"""
        assert temp_storage.count() == 0
        
        for i in range(3):
            task = CronTask.create(name=f"Task {i}", cron_expr="0 9 * * *", instruction="Test")
            temp_storage.add(task)
        
        assert temp_storage.count() == 3
    
    def test_count_enabled_returns_correct_number(self, temp_storage):
        """Test count_enabled method"""
        task1 = CronTask.create(name="Enabled", cron_expr="0 9 * * *", instruction="Test", enabled=True)
        task2 = CronTask.create(name="Disabled", cron_expr="0 10 * * *", instruction="Test", enabled=False)
        
        temp_storage.add(task1)
        temp_storage.add(task2)
        
        assert temp_storage.count_enabled() == 1
    
    def test_exists_returns_correct_status(self, temp_storage):
        """Test exists method"""
        assert not temp_storage.exists()
        
        task = CronTask.create(name="Test", cron_expr="0 9 * * *", instruction="Test")
        temp_storage.add(task)
        
        assert temp_storage.exists()
