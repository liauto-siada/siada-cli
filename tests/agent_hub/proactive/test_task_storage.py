"""
Tests for Task Storage with daily file rotation
"""

import pytest
import tempfile
import json
from pathlib import Path
from threading import Thread
from siada.agent_hub.proactive.task_storage import TaskStorage
from siada.agent_hub.proactive.models import Task, TaskList


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage(temp_storage_dir):
    """Create a TaskStorage instance with temporary directory."""
    return TaskStorage(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_task():
    """Create a sample task."""
    return Task.create(
        title="Test Task",
        description="Test Description",
        priority="high",
        needs_confirmation=False,
        source_memories=["test.md"],
        status="pending"
    )


@pytest.fixture
def sample_task_list():
    """Create a sample task list."""
    task_list = TaskList()
    task_list.add_task(Task.create(
        title="Task 1", description="Desc 1", priority="high",
        needs_confirmation=False,
        source_memories=[],
        status="pending"
    ))
    task_list.add_task(Task.create(
        title="Task 2", description="Desc 2", priority="medium",
        needs_confirmation=True,
        source_memories=[],
        status="in_progress"
    ))
    return task_list


class TestTaskStorageInitialization:
    """Test TaskStorage initialization."""
    
    def test_init_with_custom_dir(self, temp_storage_dir):
        """Test initialization with custom directory."""
        storage = TaskStorage(storage_dir=temp_storage_dir)
        
        assert storage.storage_dir == Path(temp_storage_dir)
        assert storage.storage_dir.exists()
    
    def test_get_storage_path(self, storage):
        """Test getting storage path for specific date."""
        path = storage._get_storage_path("2026-03-05")
        
        assert path.name == "tasks_2026-03-05.json"
        assert path.parent == storage.storage_dir


class TestTaskStorageSaveLoad:
    """Test save and load operations."""
    
    def test_save_and_load(self, storage, sample_task_list):
        """Test saving and loading with specific date."""
        date = "2026-03-05"
        
        success = storage.save(sample_task_list, date=date)
        assert success
        
        # Verify file exists
        expected_path = storage._get_storage_path(date)
        assert expected_path.exists()
        
        # Load
        loaded = storage.load(date=date)
        assert loaded is not None
        assert len(loaded) == 2
    
    def test_load_nonexistent_date(self, storage):
        """Test loading from nonexistent date returns None."""
        loaded = storage.load(date="2020-01-01")
        assert loaded is None


class TestTaskStorageOperations:
    """Test task-level operations."""
    
    def test_add_and_get_task(self, storage, sample_task):
        """Test adding and retrieving a task."""
        date = "2026-03-05"
        
        success = storage.add_task(sample_task, date=date)
        assert success
        assert storage.get_task_count(date=date) == 1
        
        # Verify task can be retrieved
        retrieved = storage.get_task(sample_task.id, date=date)
        assert retrieved is not None
        assert retrieved.id == sample_task.id
    
    def test_remove_task(self, storage, sample_task):
        """Test removing a task."""
        date = "2026-03-05"
        
        storage.add_task(sample_task, date=date)
        assert storage.get_task_count(date=date) == 1
        
        success = storage.remove_task(sample_task.id, date=date)
        assert success
        assert storage.get_task_count(date=date) == 0
    
    def test_filter_by_status(self, storage):
        """Test filtering tasks by status."""
        task1 = Task.create(
            title="Task 1", description="", priority="high",
            needs_confirmation=False,
            source_memories=[],
            status="pending"
        )
        task2 = Task.create(
            title="Task 2", description="", priority="high",
            needs_confirmation=False,
            source_memories=[],
            status="completed"
        )
        
        storage.add_task(task1)
        storage.add_task(task2)
        
        pending = storage.filter_by_status("pending")
        assert len(pending) == 1
        assert pending[0].status == "pending"
    
    def test_filter_by_priority(self, storage, sample_task_list):
        """Test filtering by priority."""
        storage.save(sample_task_list)
        
        high_priority = storage.filter_by_priority("high")
        assert len(high_priority) == 1
        assert high_priority[0].priority == "high"
    
    def test_thread_safe_operations(self, storage):
        """Test thread-safe concurrent operations."""
        from threading import Thread
        results = []
        date = "2026-03-05"
        
        def add_task(task_id):
            task = Task.create(
                title=f"Task {task_id}", description="", priority="high",
                needs_confirmation=False,
                source_memories=[],
                task_id=f"task-{task_id}",
                status="pending"
            )
            success = storage.add_task(task, date=date)
            results.append(success)
        
        threads = [Thread(target=add_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert all(results)
        loaded = storage.load(date=date)
        assert loaded is not None
        assert len(loaded) == 5
