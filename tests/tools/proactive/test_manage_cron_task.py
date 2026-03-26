"""
Tests for manage_cron_task tool - focused on key business logic
"""
import tempfile
from pathlib import Path
import pytest

from siada.tools.proactive.manage_cron_task import manage_cron_task_impl


@pytest.fixture
def temp_storage():
    """Create temporary storage path for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "cron_tasks.json"
        yield str(storage_path)


class TestCreateAction:
    """Test create action business logic"""
    
    def test_create_task_success(self, temp_storage):
        """Test creating a new cron task"""
        result = manage_cron_task_impl(
            action="create",
            name="Daily Report",
            cron_expr="0 9 * * *",
            instruction="Generate daily report",
            storage_path=temp_storage
        )
        
        assert "Successfully created cron task" in result
        assert "Daily Report" in result
    
    def test_create_requires_name(self, temp_storage):
        """Test that name is required"""
        with pytest.raises(ValueError, match="'name' is required"):
            manage_cron_task_impl(
                action="create",
                cron_expr="0 9 * * *",
                instruction="Test",
                storage_path=temp_storage
            )
    
    def test_create_requires_cron_expr(self, temp_storage):
        """Test that cron_expr is required"""
        with pytest.raises(ValueError, match="'cron_expr' is required"):
            manage_cron_task_impl(
                action="create",
                name="Test",
                instruction="Test",
                storage_path=temp_storage
            )
    
    def test_create_requires_instruction(self, temp_storage):
        """Test that instruction is required"""
        with pytest.raises(ValueError, match="'instruction' is required"):
            manage_cron_task_impl(
                action="create",
                name="Test",
                cron_expr="0 9 * * *",
                storage_path=temp_storage
            )
    
    def test_create_validates_cron_expr(self, temp_storage):
        """Test that invalid cron expression is rejected"""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            manage_cron_task_impl(
                action="create",
                name="Test",
                cron_expr="invalid",
                instruction="Test",
                storage_path=temp_storage
            )
    
    def test_create_disabled_task(self, temp_storage):
        """Test creating disabled task"""
        result = manage_cron_task_impl(
            action="create",
            name="Test",
            cron_expr="0 9 * * *",
            instruction="Test",
            enabled=False,
            storage_path=temp_storage
        )
        
        assert "Successfully created" in result
        assert '"enabled": false' in result


class TestUpdateAction:
    """Test update action business logic"""
    
    def test_update_task_name(self, temp_storage):
        """Test updating task name"""
        # Create task first
        create_result = manage_cron_task_impl(
            action="create",
            name="Original",
            cron_expr="0 9 * * *",
            instruction="Test",
            storage_path=temp_storage
        )
        
        # Extract task_id from result
        import json
        task_data = json.loads(create_result.split('\n', 1)[1])
        task_id = task_data['id']
        
        # Update name
        result = manage_cron_task_impl(
            action="update",
            task_id=task_id,
            name="Updated",
            storage_path=temp_storage
        )
        
        assert "Successfully updated" in result
        assert "Updated" in result
    
    def test_update_requires_task_id(self, temp_storage):
        """Test that task_id is required for update"""
        with pytest.raises(ValueError, match="'task_id' is required"):
            manage_cron_task_impl(
                action="update",
                name="Test",
                storage_path=temp_storage
            )
    
    def test_update_nonexistent_task_fails(self, temp_storage):
        """Test updating non-existent task fails"""
        with pytest.raises(ValueError, match="not found"):
            manage_cron_task_impl(
                action="update",
                task_id="nonexistent-id",
                name="Test",
                storage_path=temp_storage
            )
    
    def test_update_requires_at_least_one_field(self, temp_storage):
        """Test that at least one field must be provided"""
        # Create task first
        create_result = manage_cron_task_impl(
            action="create",
            name="Test",
            cron_expr="0 9 * * *",
            instruction="Test",
            storage_path=temp_storage
        )
        
        import json
        task_data = json.loads(create_result.split('\n', 1)[1])
        task_id = task_data['id']
        
        # Try update with no fields
        with pytest.raises(ValueError, match="At least one field must be provided"):
            manage_cron_task_impl(
                action="update",
                task_id=task_id,
                storage_path=temp_storage
            )
    
    def test_update_validates_new_cron_expr(self, temp_storage):
        """Test that new cron expression is validated"""
        # Create task
        create_result = manage_cron_task_impl(
            action="create",
            name="Test",
            cron_expr="0 9 * * *",
            instruction="Test",
            storage_path=temp_storage
        )
        
        import json
        task_data = json.loads(create_result.split('\n', 1)[1])
        task_id = task_data['id']
        
        # Try invalid cron expr
        with pytest.raises(ValueError, match="Invalid cron expression"):
            manage_cron_task_impl(
                action="update",
                task_id=task_id,
                cron_expr="invalid",
                storage_path=temp_storage
            )
    
    def test_update_multiple_fields(self, temp_storage):
        """Test updating multiple fields at once"""
        # Create task
        create_result = manage_cron_task_impl(
            action="create",
            name="Original",
            cron_expr="0 9 * * *",
            instruction="Original instruction",
            storage_path=temp_storage
        )
        
        import json
        task_data = json.loads(create_result.split('\n', 1)[1])
        task_id = task_data['id']
        
        # Update multiple fields
        result = manage_cron_task_impl(
            action="update",
            task_id=task_id,
            name="Updated",
            cron_expr="0 18 * * *",
            instruction="Updated instruction",
            enabled=False,
            storage_path=temp_storage
        )
        
        assert "Successfully updated" in result
        assert "Updated" in result
        assert "0 18 * * *" in result
        assert '"enabled": false' in result


class TestDeleteAction:
    """Test delete action business logic"""
    
    def test_delete_task_success(self, temp_storage):
        """Test deleting a task"""
        # Create task
        create_result = manage_cron_task_impl(
            action="create",
            name="To Delete",
            cron_expr="0 9 * * *",
            instruction="Test",
            storage_path=temp_storage
        )
        
        import json
        task_data = json.loads(create_result.split('\n', 1)[1])
        task_id = task_data['id']
        
        # Delete task
        result = manage_cron_task_impl(
            action="delete",
            task_id=task_id,
            storage_path=temp_storage
        )
        
        assert "Successfully deleted" in result
        assert task_id in result
        assert "To Delete" in result
    
    def test_delete_requires_task_id(self, temp_storage):
        """Test that task_id is required for delete"""
        with pytest.raises(ValueError, match="'task_id' is required"):
            manage_cron_task_impl(
                action="delete",
                storage_path=temp_storage
            )
    
    def test_delete_nonexistent_task_fails(self, temp_storage):
        """Test deleting non-existent task fails"""
        with pytest.raises(ValueError, match="not found"):
            manage_cron_task_impl(
                action="delete",
                task_id="nonexistent-id",
                storage_path=temp_storage
            )


class TestListAction:
    """Test list action business logic"""
    
    def test_list_empty(self, temp_storage):
        """Test listing when no tasks exist"""
        result = manage_cron_task_impl(
            action="list",
            storage_path=temp_storage
        )
        
        assert "No cron tasks found" in result
    
    def test_list_all_tasks(self, temp_storage):
        """Test listing all tasks"""
        # Create multiple tasks
        for i in range(3):
            manage_cron_task_impl(
                action="create",
                name=f"Task {i}",
                cron_expr="0 9 * * *",
                instruction="Test",
                storage_path=temp_storage
            )
        
        result = manage_cron_task_impl(
            action="list",
            storage_path=temp_storage
        )
        
        assert "Task 0" in result
        assert "Task 1" in result
        assert "Task 2" in result
        assert "Total: 3 task(s)" in result
    
    def test_list_enabled_only(self, temp_storage):
        """Test listing only enabled tasks"""
        # Create enabled task
        manage_cron_task_impl(
            action="create",
            name="Enabled Task",
            cron_expr="0 9 * * *",
            instruction="Test",
            enabled=True,
            storage_path=temp_storage
        )
        
        # Create disabled task
        manage_cron_task_impl(
            action="create",
            name="Disabled Task",
            cron_expr="0 10 * * *",
            instruction="Test",
            enabled=False,
            storage_path=temp_storage
        )
        
        result = manage_cron_task_impl(
            action="list",
            enabled_only=True,
            storage_path=temp_storage
        )
        
        assert "Enabled Task" in result
        assert "Disabled Task" not in result
        assert "Total: 1 task(s)" in result
    
    def test_list_invalid_sort_by_fails(self, temp_storage):
        """Test that invalid sort_by parameter fails"""
        with pytest.raises(ValueError, match="Invalid sort_by"):
            manage_cron_task_impl(
                action="list",
                sort_by="invalid",
                storage_path=temp_storage
            )


class TestActionValidation:
    """Test action parameter validation"""
    
    def test_invalid_action_fails(self, temp_storage):
        """Test that invalid action parameter fails"""
        with pytest.raises(ValueError, match="Invalid action"):
            manage_cron_task_impl(
                action="invalid",
                storage_path=temp_storage
            )
