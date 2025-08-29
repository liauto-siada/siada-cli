import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from siada.services.git_service import GitService

# Skip tests if GitPython is not available
try:
    import git
    from git import Repo, InvalidGitRepositoryError, GitCommandError
    from git.exc import NoSuchPathError, BadName
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


@unittest.skipUnless(GIT_AVAILABLE, "GitPython not available")
class TestGitService(unittest.TestCase):
    """Test cases for GitService class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directories for testing
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir) / "test_project"
        self.shadow_repo_dir = Path(self.temp_dir) / "shadow_repo"
        
        # Create test project directory
        self.project_root.mkdir(parents=True, exist_ok=True)
        
        # Create some test files
        (self.project_root / "test_file.txt").write_text("Initial content")
        (self.project_root / "subdir").mkdir(exist_ok=True)
        (self.project_root / "subdir" / "nested_file.py").write_text("print('hello')")
        
        # Create a test .gitignore file
        (self.project_root / ".gitignore").write_text("*.log\n__pycache__/\n")
        
        self.git_service = GitService(str(self.project_root), str(self.shadow_repo_dir))
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_init(self):
        """Test GitService initialization"""
        self.assertEqual(self.git_service.project_root, self.project_root.resolve())
        self.assertEqual(self.git_service.shadow_repo_dir, self.shadow_repo_dir.resolve())
        self.assertIsNone(self.git_service._repo)
    
    @patch('siada.services.git_service.subprocess.run')
    def test_verify_git_availability_success(self, mock_run):
        """Test git availability verification when git is available"""
        mock_run.return_value.returncode = 0
        
        result = self.git_service.verify_git_availability()
        
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["git", "--version"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
    
    @patch('siada.services.git_service.subprocess.run')
    def test_verify_git_availability_failure(self, mock_run):
        """Test git availability verification when git is not available"""
        mock_run.side_effect = FileNotFoundError()
        
        result = self.git_service.verify_git_availability()
        
        self.assertFalse(result)
    
    @patch('siada.services.git_service.subprocess.run')
    def test_verify_git_availability_command_failure(self, mock_run):
        """Test git availability verification when git command fails"""
        mock_run.return_value.returncode = 1
        
        result = self.git_service.verify_git_availability()
        
        self.assertFalse(result)
    
    @patch('siada.services.git_service.GIT_AVAILABLE', False)
    def test_verify_git_availability_no_gitpython(self):
        """Test git availability verification when GitPython is not available"""
        result = self.git_service.verify_git_availability()
        self.assertFalse(result)
    
    def test_initialize_success(self):
        """Test successful GitService initialization"""
        # Mock git availability check to return True
        with patch.object(self.git_service, 'verify_git_availability', return_value=True):
            with patch.object(self.git_service, 'setup_shadow_git_repository'):
                self.git_service.initialize()
    
    def test_initialize_git_not_available(self):
        """Test GitService initialization when git is not available"""
        with patch.object(self.git_service, 'verify_git_availability', return_value=False):
            with self.assertRaises(RuntimeError) as context:
                self.git_service.initialize()
            
            self.assertIn("GitPython is not installed", str(context.exception))
    
    def test_setup_shadow_git_repository_new_repo(self):
        """Test setting up a new shadow git repository"""
        self.git_service.setup_shadow_git_repository()
        
        # Verify shadow directory was created
        self.assertTrue(self.shadow_repo_dir.exists())
        
        # Verify git config file was created
        git_config_path = self.shadow_repo_dir / ".gitconfig"
        self.assertTrue(git_config_path.exists())
        
        config_content = git_config_path.read_text()
        self.assertIn("name = Siada CLI", config_content)
        self.assertIn("email = siada-cli@siada.com", config_content)
        
        # Verify .gitignore was copied
        shadow_gitignore = self.shadow_repo_dir / ".gitignore"
        self.assertTrue(shadow_gitignore.exists())
        self.assertEqual(shadow_gitignore.read_text(), "*.log\n__pycache__/\n")
        
        # Verify repository was initialized
        self.assertIsNotNone(self.git_service._repo)
        self.assertTrue((self.shadow_repo_dir / ".git").exists())
    
    def test_setup_shadow_git_repository_existing_repo(self):
        """Test setting up shadow repository when one already exists"""
        # First setup
        self.git_service.setup_shadow_git_repository()
        
        # Create a new GitService instance pointing to the same shadow repo
        new_git_service = GitService(str(self.project_root), str(self.shadow_repo_dir))
        new_git_service.setup_shadow_git_repository()
        
        # Should reuse existing repository
        self.assertIsNotNone(new_git_service._repo)
    
    def test_setup_shadow_git_repository_no_user_gitignore(self):
        """Test setting up shadow repository when user has no .gitignore"""
        # Remove user's .gitignore
        (self.project_root / ".gitignore").unlink()
        
        self.git_service.setup_shadow_git_repository()
        
        # Verify empty .gitignore was created
        shadow_gitignore = self.shadow_repo_dir / ".gitignore"
        self.assertTrue(shadow_gitignore.exists())
        self.assertEqual(shadow_gitignore.read_text(), "")
    
    def test_shadow_git_repository_property(self):
        """Test shadow_git_repository property"""
        # Before setup
        self.assertIsNone(self.git_service.shadow_git_repository)
        
        # After setup
        self.git_service.setup_shadow_git_repository()
        shadow_repo = self.git_service.shadow_git_repository
        
        self.assertIsNotNone(shadow_repo)
        self.assertIsInstance(shadow_repo, Repo)
    
    def test_get_current_commit_hash(self):
        """Test getting current commit hash"""
        self.git_service.setup_shadow_git_repository()
        
        # Create a snapshot first
        commit_hash = self.git_service.create_snapshot("Test commit")
        
        # Get current commit hash
        current_hash = self.git_service.get_current_commit_hash()
        
        self.assertEqual(current_hash, commit_hash)
        self.assertEqual(len(current_hash), 40)  # SHA-1 hash length
    
    def test_get_current_commit_hash_not_initialized(self):
        """Test getting current commit hash when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.get_current_commit_hash()
        
        self.assertIn("Repository not initialized", str(context.exception))
    
    def test_create_snapshot(self):
        """Test creating a snapshot"""
        self.git_service.setup_shadow_git_repository()
        
        commit_hash = self.git_service.create_snapshot("Test snapshot")
        
        self.assertIsNotNone(commit_hash)
        self.assertEqual(len(commit_hash), 40)  # SHA-1 hash length
        
        # Verify commit exists
        self.assertTrue(self.git_service.snapshot_exists(commit_hash))
    
    def test_create_snapshot_not_initialized(self):
        """Test creating snapshot when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.create_snapshot("Test")
        
        self.assertIn("Repository not initialized", str(context.exception))
    
    def test_restore_project_from_snapshot(self):
        """Test restoring project from a snapshot"""
        self.git_service.setup_shadow_git_repository()
        
        # Create initial snapshot
        initial_content = (self.project_root / "test_file.txt").read_text()
        commit_hash = self.git_service.create_snapshot("Initial snapshot")
        
        # Modify file
        (self.project_root / "test_file.txt").write_text("Modified content")
        self.assertNotEqual((self.project_root / "test_file.txt").read_text(), initial_content)
        
        # Restore from snapshot
        self.git_service.restore_project_from_snapshot(commit_hash)
        
        # Verify file was restored
        restored_content = (self.project_root / "test_file.txt").read_text()
        self.assertEqual(restored_content, initial_content)
    
    def test_restore_project_from_snapshot_not_initialized(self):
        """Test restoring snapshot when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.restore_project_from_snapshot("abc123")
        
        self.assertIn("Repository not initialized", str(context.exception))
    
    def test_list_snapshots(self):
        """Test listing snapshots"""
        self.git_service.setup_shadow_git_repository()
        
        # Create multiple snapshots
        self.git_service.create_snapshot("First commit")
        
        # Modify file and create another snapshot
        (self.project_root / "test_file.txt").write_text("Second version")
        commit2 = self.git_service.create_snapshot("Second commit")
        
        # List snapshots
        snapshots = self.git_service.list_snapshots()
        
        self.assertEqual(len(snapshots), 3)  # 2 created + 1 initial empty commit
        
        # Verify snapshot structure
        latest_snapshot = snapshots[0]  # Most recent first
        self.assertEqual(latest_snapshot['hash'], commit2)
        self.assertEqual(latest_snapshot['message'], 'Second commit')
        self.assertIn('author', latest_snapshot)
        self.assertIn('date', latest_snapshot)
    
    def test_list_snapshots_with_limit(self):
        """Test listing snapshots with limit"""
        self.git_service.setup_shadow_git_repository()
        
        # Create multiple snapshots
        for i in range(5):
            (self.project_root / f"file_{i}.txt").write_text(f"Content {i}")
            self.git_service.create_snapshot(f"Commit {i}")
        
        # List with limit
        snapshots = self.git_service.list_snapshots(limit=3)
        
        self.assertEqual(len(snapshots), 3)
    
    def test_list_snapshots_not_initialized(self):
        """Test listing snapshots when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.list_snapshots()
        
        self.assertIn("Repository not initialized", str(context.exception))
    
    def test_get_snapshot_diff(self):
        """Test getting snapshot diff"""
        self.git_service.setup_shadow_git_repository()
        
        # Create initial snapshot
        self.git_service.create_snapshot("Initial commit")
        
        # Create a file and snapshot it
        (self.project_root / "test_file.txt").write_text("Initial content")
        commit2 = self.git_service.create_snapshot("Add test file")
        
        # Now modify the file in working directory
        (self.project_root / "test_file.txt").write_text("Modified content for diff test")
        
        # Get diff from commit2 to current working directory
        diff = self.git_service.get_snapshot_diff(commit2)
        
        self.assertIsInstance(diff, str)
        # Check that diff shows the working directory changes
        self.assertIn("Modified content for diff test", diff)
        self.assertIn("Initial content", diff)  # Should show what was replaced
        self.assertIn("@@", diff)  # Diff hunk marker
    
    def test_get_snapshot_diff_with_base(self):
        """Test getting snapshot diff with specific base commit"""
        self.git_service.setup_shadow_git_repository()
        
        # Create snapshots
        commit1 = self.git_service.create_snapshot("Base commit")
        
        (self.project_root / "test_file.txt").write_text("Modified content")
        commit2 = self.git_service.create_snapshot("Target commit")
        
        # Get diff between specific commits
        diff = self.git_service.get_snapshot_diff(commit2, commit1)
        
        self.assertIsInstance(diff, str)
        # Check that diff contains the content changes
        self.assertIn("Modified content", diff)
        self.assertIn("@@", diff)  # Diff hunk marker
    
    def test_snapshot_exists(self):
        """Test checking if snapshot exists"""
        self.git_service.setup_shadow_git_repository()
        
        commit_hash = self.git_service.create_snapshot("Test commit")
        
        # Test existing snapshot
        self.assertTrue(self.git_service.snapshot_exists(commit_hash))
        
        # Test non-existing snapshot
        self.assertFalse(self.git_service.snapshot_exists("nonexistent123"))
    
    def test_snapshot_exists_not_initialized(self):
        """Test checking snapshot exists when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.snapshot_exists("abc123")
        
        self.assertIn("Repository not initialized", str(context.exception))
    
    def test_get_modified_files(self):
        """Test getting list of modified files"""
        self.git_service.setup_shadow_git_repository()
        
        # Create initial snapshot
        self.git_service.create_snapshot("Initial commit")
        
        # Modify existing file
        (self.project_root / "test_file.txt").write_text("Modified content")
        
        # Add new file
        (self.project_root / "new_file.txt").write_text("New file content")
        
        # Delete a file
        (self.project_root / "subdir" / "nested_file.py").unlink()
        
        # Get modified files
        modified_files = self.git_service.get_modified_files()
        
        self.assertIsInstance(modified_files, list)
        # Should contain modified and new files
        file_set = set(modified_files)
        self.assertIn("test_file.txt", file_set)
        self.assertIn("new_file.txt", file_set)
        self.assertIn("subdir/nested_file.py", file_set)
    
    def test_get_modified_files_empty(self):
        """Test getting modified files when none exist"""
        self.git_service.setup_shadow_git_repository()
        
        # Create snapshot of current state
        self.git_service.create_snapshot("Clean state")
        
        # No modifications
        modified_files = self.git_service.get_modified_files()
        
        self.assertEqual(modified_files, [])
    
    def test_get_modified_files_not_initialized(self):
        """Test getting modified files when not initialized"""
        with self.assertRaises(RuntimeError) as context:
            self.git_service.get_modified_files()
        
        self.assertIn("Repository not initialized", str(context.exception))


class TestGitServiceMocked(unittest.TestCase):
    """Test cases for GitService with mocked dependencies"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir) / "test_project"
        self.shadow_repo_dir = Path(self.temp_dir) / "shadow_repo"
        
        self.project_root.mkdir(parents=True, exist_ok=True)
        
        self.git_service = GitService(str(self.project_root), str(self.shadow_repo_dir))
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('siada.services.git_service.GIT_AVAILABLE', False)
    def test_verify_git_availability_no_gitpython_available(self):
        """Test when GitPython module is not available"""
        result = self.git_service.verify_git_availability()
        self.assertFalse(result)
    
    @patch('siada.services.git_service.Repo')
    def test_shadow_git_repository_property_error(self, mock_repo):
        """Test shadow_git_repository property when repo creation fails"""
        # Setup initial repo
        self.git_service._repo = MagicMock()
        
        # Mock Repo constructor to raise exception
        mock_repo.side_effect = InvalidGitRepositoryError("Test error")
        
        result = self.git_service.shadow_git_repository
        self.assertIsNone(result)
    
    def test_is_git_repository_true(self):
        """Test _is_git_repository method returns True for valid repo"""
        with patch('siada.services.git_service.Repo') as mock_repo:
            mock_repo.return_value = MagicMock()
            
            result = self.git_service._is_git_repository("/valid/repo")
            self.assertTrue(result)
    
    def test_is_git_repository_false(self):
        """Test _is_git_repository method returns False for invalid repo"""
        with patch('siada.services.git_service.Repo') as mock_repo:
            mock_repo.side_effect = InvalidGitRepositoryError("Not a repo")
            
            result = self.git_service._is_git_repository("/invalid/repo")
            self.assertFalse(result)
    
    @patch('siada.services.git_service.Repo')
    def test_setup_shadow_git_repository_with_git_command_error(self, mock_repo):
        """Test setup when git commit fails"""
        mock_repo_instance = MagicMock()
        mock_repo.init.return_value = mock_repo_instance
        mock_repo_instance.git.commit.side_effect = GitCommandError("commit", "failed")
        
        # Should not raise exception, just log warning
        self.git_service.setup_shadow_git_repository()
        
        self.assertIsNotNone(self.git_service._repo)


@unittest.skipUnless(GIT_AVAILABLE, "GitPython not available")
class TestGitPythonAPICompatibility(unittest.TestCase):
    """Test GitPython API compatibility and functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.temp_dir) / "test_repo"
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_gitpython_repo_init(self):
        """Test GitPython repository initialization"""
        repo = Repo.init(str(self.repo_path))
        
        self.assertIsNotNone(repo)
        self.assertTrue((self.repo_path / ".git").exists())
        self.assertEqual(repo.working_dir, str(self.repo_path))
    
    def test_gitpython_config_operations(self):
        """Test GitPython configuration operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Test configuration writer
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
            config.set_value("commit", "gpgsign", False)
        
        # Test configuration reader
        with repo.config_reader() as config:
            self.assertEqual(config.get_value("user", "name"), "Test User")
            self.assertEqual(config.get_value("user", "email"), "test@example.com")
            self.assertFalse(config.get_value("commit", "gpgsign"))
    
    def test_gitpython_file_operations(self):
        """Test GitPython file add and commit operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create test file
        test_file = self.repo_path / "test.txt"
        test_file.write_text("Hello GitPython!")
        
        # Add file to index
        repo.index.add([str(test_file)])
        
        # Create commit
        commit = repo.index.commit("Initial commit")
        
        self.assertIsNotNone(commit)
        self.assertEqual(commit.message, "Initial commit")
        self.assertEqual(len(commit.hexsha), 40)  # SHA-1 hash length
    
    def test_gitpython_status_operations(self):
        """Test GitPython status operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create and commit initial file
        test_file = self.repo_path / "test.txt"
        test_file.write_text("Initial content")
        repo.index.add([str(test_file)])
        repo.index.commit("Initial commit")
        
        # Modify file
        test_file.write_text("Modified content")
        
        # Create new file
        new_file = self.repo_path / "new.txt"
        new_file.write_text("New file")
        
        # Test git status via porcelain format
        status_output = repo.git.status("--porcelain")
        
        self.assertIn("test.txt", status_output)  # Modified file
        self.assertIn("new.txt", status_output)   # Untracked file
    
    def test_gitpython_commit_iteration(self):
        """Test GitPython commit iteration"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create multiple commits
        for i in range(3):
            test_file = self.repo_path / f"file_{i}.txt"
            test_file.write_text(f"Content {i}")
            repo.index.add([str(test_file)])
            repo.index.commit(f"Commit {i}")
        
        # Test commit iteration
        commits = list(repo.iter_commits(max_count=5))
        
        self.assertEqual(len(commits), 3)
        self.assertEqual(commits[0].message, "Commit 2")  # Most recent first
        self.assertEqual(commits[-1].message, "Commit 0")  # Oldest last
    
    def test_gitpython_diff_operations(self):
        """Test GitPython diff operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create initial commit
        test_file = self.repo_path / "test.txt"
        test_file.write_text("Original content")
        repo.index.add([str(test_file)])
        commit1 = repo.index.commit("Initial commit")
        
        # Modify and commit again
        test_file.write_text("Modified content")
        repo.index.add([str(test_file)])
        commit2 = repo.index.commit("Modified commit")
        
        # Test diff between commits
        diff = commit1.diff(commit2, create_patch=True)
        
        self.assertIsNotNone(diff)
        self.assertTrue(len(diff) > 0)
        
        # Test diff content
        diff_item = diff[0]
        self.assertIsNotNone(diff_item.diff)
        diff_text = diff_item.diff.decode('utf-8')
        self.assertIn("Original content", diff_text)
        self.assertIn("Modified content", diff_text)
    
    def test_gitpython_restore_operations(self):
        """Test GitPython restore operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create initial commit
        test_file = self.repo_path / "test.txt"
        original_content = "Original content"
        test_file.write_text(original_content)
        repo.index.add([str(test_file)])
        commit_hash = repo.index.commit("Initial commit").hexsha
        
        # Modify file
        test_file.write_text("Modified content")
        
        # Test restore operation
        repo.git.restore("--source", commit_hash, ".")
        
        # Verify file was restored
        restored_content = test_file.read_text()
        self.assertEqual(restored_content, original_content)
    
    def test_gitpython_environment_isolation(self):
        """Test GitPython environment variable handling"""
        repo = Repo.init(str(self.repo_path))
        
        # Test environment update
        original_env = dict(repo.git.environment())
        
        # Update environment
        repo.git.update_environment(
            GIT_AUTHOR_NAME="Test Author",
            GIT_COMMITTER_NAME="Test Committer"
        )
        
        # Verify environment was updated
        updated_env = repo.git.environment()
        self.assertEqual(updated_env.get("GIT_AUTHOR_NAME"), "Test Author")
        self.assertEqual(updated_env.get("GIT_COMMITTER_NAME"), "Test Committer")
        
        # Verify original environment values are preserved
        for key, value in original_env.items():
            if key not in ["GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"]:
                self.assertEqual(updated_env.get(key), value)
    
    def test_gitpython_error_handling(self):
        """Test GitPython error handling"""
        # Test no such path error for non-existent path
        with self.assertRaises(NoSuchPathError):
            Repo("/nonexistent/path")
        
        # Test invalid repository error for non-git directory
        non_git_dir = Path(self.temp_dir) / "not_a_git_repo"
        non_git_dir.mkdir(exist_ok=True)
        with self.assertRaises(InvalidGitRepositoryError):
            Repo(str(non_git_dir))
        
        # Test git command error
        repo = Repo.init(str(self.repo_path))
        
        with self.assertRaises(GitCommandError):
            repo.git.commit("--invalid-option")
    
    def test_gitpython_clean_operations(self):
        """Test GitPython clean operations"""
        repo = Repo.init(str(self.repo_path))
        
        # Configure repo
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")
        
        # Create tracked file and commit
        tracked_file = self.repo_path / "tracked.txt"
        tracked_file.write_text("Tracked content")
        repo.index.add([str(tracked_file)])
        repo.index.commit("Initial commit")
        
        # Create untracked file
        untracked_file = self.repo_path / "untracked.txt"
        untracked_file.write_text("Untracked content")
        
        # Verify untracked file exists
        self.assertTrue(untracked_file.exists())
        
        # Test clean operation (dry run first)
        try:
            clean_output = repo.git.clean("-n", "-f", "-d")
            self.assertIn("untracked.txt", clean_output)
        except GitCommandError:
            # Clean may fail if no files to clean, which is also valid
            pass
        
        # Actual clean
        try:
            repo.git.clean("-f", "-d")
        except GitCommandError:
            # Clean may fail if no files to clean, which is also valid
            pass


if __name__ == '__main__':
    unittest.main()