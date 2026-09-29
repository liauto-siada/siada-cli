"""
Git service for checkpointing functionality.

This service provides git-based checkpointing capabilities for tracking file changes
and creating/restoring snapshots during agent execution.
"""

import shutil
from pathlib import Path
from typing import ClassVar, Optional

from siada.foundation.logging import logger


GIT_AVAILABLE = None  #


def _load_git() -> bool:
    """Import GitPython on first use, binding its symbols to module globals."""
    global Repo, InvalidGitRepositoryError, GitCommandError
    global NoSuchPathError, BadName, GIT_AVAILABLE
    if GIT_AVAILABLE is not None:
        return GIT_AVAILABLE
    try:
        from git import Repo, InvalidGitRepositoryError, GitCommandError
        from git.exc import NoSuchPathError, BadName
        GIT_AVAILABLE = True
    except ImportError:
        GIT_AVAILABLE = False
    return GIT_AVAILABLE

class GitService:
    """Git service for managing project checkpoints using a shadow git repository."""

    # Process-wide cache for the (expensive) "is git usable" check. `git
    # --version` is a real fork/exec; since the git executable on PATH
    # cannot change during the lifetime of a process, we only need to
    # determine availability once per process and reuse the result for
    # every GitService instance / session created afterwards.
    _git_available_cache: ClassVar[Optional[bool]] = None

    def __init__(self, project_root: str, shadow_repo_dir: str):
        """
        Initialize GitService.
        
        Args:
            project_root: Path to the project root directory
            shadow_repo_dir: Path to the shadow repository directory
        """
        self.project_root = Path(project_root).resolve()
        self.shadow_repo_dir = Path(shadow_repo_dir).resolve()
        self._repo: Optional[Repo] = None
        # Tracks whether initialize() has already run. For a brand-new
        # shadow repository, GitService.initialize() still forks real `git`
        # subprocesses (`git init`, the initial empty commit), so we keep it
        # idempotent and lazy: it is only actually executed on first real use
        # (see _ensure_initialized / shadow_git_repository), not eagerly at
        # construction time. This keeps CheckPointTracker/GitService
        # construction (and therefore create_session()) cheap for sessions
        # that never end up needing a checkpoint.
        #
        # Note: the git-availability check (previously a `git --version`
        # fork/exec) and the "open existing shadow repo + read HEAD" step
        # (previously a forced `repo.head.commit` resolution) have both been
        # optimized away below (see verify_git_availability and
        # setup_shadow_git_repository) so that even when initialize() does
        # run, it no longer pays for those extra subprocess forks.
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize the git service by verifying git availability and setting up shadow repository.

        Idempotent: calling this multiple times only does the actual work once.

        Raises:
            RuntimeError: If git is not available or initialization fails
        """
        if self._initialized:
            return

        git_available = self.verify_git_availability()
        if not git_available:
            raise RuntimeError(
                "Checkpointing is enabled, but GitPython is not installed. "
                "Please install GitPython or disable checkpointing to continue."
            )
        self.setup_shadow_git_repository()
        self._initialized = True

    def _ensure_initialized(self) -> None:
        """Lazily run initialize() on first real use of the shadow repository."""
        if not self._initialized:
            self.initialize()


    def verify_git_availability(self) -> bool:
        """
        Check if both GitPython and git executable are available on the system.

        Performance note: the previous implementation forked a real `git`
        subprocess (`git --version`) on every call. That fork/exec is one of
        the 3-4 real git subprocess calls that used to happen inside
        create_session()/initialize(). Since the git executable resolved
        from PATH cannot change during the lifetime of the current process,
        we now:
          1. Resolve availability via `shutil.which("git")`, which is a pure
             Python PATH lookup and never forks a subprocess.
          2. Cache the result at the class level so it is computed at most
             once per process, regardless of how many GitService instances
             / sessions are created afterwards.

        Returns:
            True if both GitPython and git executable are available, False otherwise
        """
        if not _load_git():
            return False

        if GitService._git_available_cache is not None:
            return GitService._git_available_cache

        available = shutil.which("git") is not None
        GitService._git_available_cache = available
        return available


    def setup_shadow_git_repository(self) -> None:
        """
        Create a shadow git repository for checkpointing.

        This creates a separate git repository that tracks the project files
        without interfering with the user's existing git repository.
        """
        if not _load_git():
            raise RuntimeError(
                "GitPython is not installed. "
                "Please install GitPython or disable checkpointing to continue."
            )

        # Create history directory
        self.shadow_repo_dir.mkdir(parents=True, exist_ok=True)

        # Create dedicated git config to avoid inheriting user settings
        git_config_path = self.shadow_repo_dir / ".gitconfig"
        git_config_content = (
            "[user]\n"
            "  name = Siada CLI\n"
            "  email = siada-cli@siada.com\n"
            "[commit]\n"
            "  gpgsign = false\n"
        )
        git_config_path.write_text(git_config_content)

        # Check if repo already exists using proper repo detection.
        #
        # Performance note: we intentionally avoid forcing resolution of
        # `repo.head.commit` here. The `Repo()` constructor already
        # validates that `shadow_repo_dir` contains a well-formed `.git`
        # directory (raising InvalidGitRepositoryError/NoSuchPathError
        # otherwise), which is enough to safely reuse the existing shadow
        # repository. Eagerly walking HEAD -> ref -> commit object on every
        # single session/checkpoint init was one of the extra git
        # operations contributing to create_session() latency, and it adds
        # no real safety here: any genuinely corrupted repository will
        # still surface a clear GitCommandError/BadName on first actual use
        # (e.g. create_snapshot / get_current_commit_hash), which is
        # already handled by those call sites.
        try:
            # Try to open existing repository
            self._repo = Repo(str(self.shadow_repo_dir))
            logger.info(f"Using existing shadow repository at {self.shadow_repo_dir}")
        except (InvalidGitRepositoryError, BadName, NoSuchPathError):
            # Initialize new repository
            self._repo = Repo.init(str(self.shadow_repo_dir), initial_branch="main")
            logger.info(f"Initialized new shadow repository at {self.shadow_repo_dir}")

            # Set up environment for shadow git repository
            with self._repo.config_writer() as config:
                config.set_value("user", "name", "Siada CLI")
                config.set_value("user", "email", "siada-cli@siada.com")
                config.set_value("commit", "gpgsign", False)

            # Create initial empty commit
            try:
                self._repo.git.commit("--allow-empty", "--no-verify", "-m", "Initial commit")
            except GitCommandError as e:
                logger.warning(f"Failed to create initial commit: {e}")

        # Copy user's .gitignore if it exists (match TypeScript behavior)
        user_gitignore = self.project_root / ".gitignore"
        shadow_gitignore = self.shadow_repo_dir / ".gitignore"

        user_gitignore_content = ""
        if user_gitignore.exists():
            try:
                user_gitignore_content = user_gitignore.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Could not read user .gitignore: {e}")
                user_gitignore_content = ""

        # Always write the gitignore file (even if empty)
        shadow_gitignore.write_text(user_gitignore_content, encoding='utf-8')

    @property
    def shadow_git_repository(self) -> Optional['Repo']:
        """
        Get a repository instance configured for shadow operations.
        
        This property returns a repository instance with proper environment
        variables set for isolated shadow repository operations.
        
        Returns:
            Configured Repo instance or None if not initialized
        """
        self._ensure_initialized()
        if not self._repo:
            return None


        try:
            # Create a new repo instance with environment isolation
            repo_with_env = Repo(str(self.shadow_repo_dir))
            repo_with_env.git.update_environment(
                GIT_DIR=str(self.shadow_repo_dir / ".git"),
                GIT_WORK_TREE=str(self.project_root),
                HOME=str(self.shadow_repo_dir),
                XDG_CONFIG_HOME=str(self.shadow_repo_dir),
                PAGER='cat'  # Disable pager for programmatic access
            )
            return repo_with_env
        except (InvalidGitRepositoryError, NoSuchPathError) as e:
            logger.error(f"Failed to create shadow repository instance: {e}")
            return None

    def _is_git_repository(self, path: str) -> bool:
        """Check if the given path is a git repository."""
        if not _load_git():
            return False
        try:
            Repo(path)
            return True
        except (InvalidGitRepositoryError, NoSuchPathError):
            return False

    def get_current_commit_hash(self) -> str:
        """
        Get the current commit hash of the shadow repository using raw git commands.
        
        Returns:
            Current commit hash as string
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        try:
            # Use raw git command to get current commit hash
            hash_output = repo.git.rev_parse(["HEAD"])
            return hash_output.strip()
        except (GitCommandError, BadName) as e:
            raise RuntimeError(f"Failed to get current commit hash: {e}")

    def create_snapshot(self, message: str) -> str:
        """
        Create a snapshot of the current project state.
        
        Args:
            message: Commit message for the snapshot
            
        Returns:
            Commit hash of the created snapshot
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        try:
            # Add all files to staging using the shadow repository
            repo.git.add(".", "--ignore-errors")

            # Create commit with --no-verify and --allow-empty
            repo.git.commit("--no-verify", "--allow-empty", "-m", message)
            
            # Get the commit hash of HEAD
            return repo.git.rev_parse("HEAD")

        except (GitCommandError, OSError) as e:
            raise RuntimeError(f"Failed to create snapshot: {e}")

    def restore_project_from_snapshot(self, commit_hash: str) -> None:
        """
        Restore the project to a specific snapshot.
        
        Args:
            commit_hash: Hash of the commit to restore to
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        try:
            # Restore files from the specified commit using restore
            repo.git.restore(["--source", commit_hash, "."])

            # Remove any untracked files that were introduced after the snapshot
            try:
                repo.git.clean("-f", "-d")
            except GitCommandError:
                # Don't fail if no files to clean
                pass

        except (GitCommandError, BadName) as e:
            raise RuntimeError(f"Failed to restore snapshot {commit_hash}: {e}")

    def list_snapshots(self, limit: int = 10) -> list[dict]:
        """
        List recent snapshots with metadata.
        
        Args:
            limit: Maximum number of snapshots to return
            
        Returns:
            List of snapshot information dictionaries
        """
        self._ensure_initialized()
        if not self._repo:
            raise RuntimeError("Repository not initialized")


        try:
            snapshots = []
            for commit in self._repo.iter_commits(max_count=limit):
                snapshots.append({
                    'hash': commit.hexsha,
                    'author': str(commit.author),
                    'date': commit.committed_datetime.isoformat(),
                    'message': commit.message.strip()
                })
            return snapshots
        except (GitCommandError, BadName):
            # Return empty list if no commits exist or invalid references
            return []

    def get_snapshot_diff(self, commit_hash: str, base_commit: Optional[str] = None) -> str:
        """
        Get the diff for a specific snapshot.
        
        Args:
            commit_hash: Hash of the commit to get diff for
            base_commit: Base commit to compare against (defaults to working directory)
            
        Returns:
            Diff output as string
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        try:
            if base_commit:
                # Compare between two specific commits
                diff_output = repo.git.diff(base_commit, commit_hash)
            else:
                # Compare specified commit with current working directory
                # This shows all changes from that snapshot to now
                diff_output = repo.git.diff(commit_hash)
                
            return diff_output

        except (GitCommandError, ValueError, BadName) as e:
            raise RuntimeError(f"Failed to get diff for snapshot {commit_hash}: {e}")

    def snapshot_exists(self, commit_hash: str) -> bool:
        """
        Check if a snapshot with the given commit hash exists.
        
        Args:
            commit_hash: Hash of the commit to check
            
        Returns:
            True if snapshot exists, False otherwise
        """
        self._ensure_initialized()
        if not self._repo:
            raise RuntimeError("Repository not initialized")


        try:
            self._repo.commit(commit_hash)
            return True
        except (GitCommandError, ValueError, BadName):
            return False

    def get_modified_files(self) -> list[str]:
        """
        Get list of modified files in the working directory.
        
        Returns:
            List of file paths that have been modified, added, or deleted
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        modified_files = []
        try:
            # Get status output using porcelain format for stable parsing
            status_output = repo.git.status("--porcelain")
            if status_output:
                for line in status_output.strip().split('\n'):
                    if line.strip():
                        # Extract filename from git status output (format: XY filename)
                        # Where X is the status in staging area, Y is status in working tree
                        parts = line.strip().split(maxsplit=1)
                        if len(parts) > 1:
                            # Handle renamed files (format: R  old_name -> new_name)
                            filename = parts[1]
                            if ' -> ' in filename:
                                # For renamed files, use the new name
                                filename = filename.split(' -> ')[1]
                            modified_files.append(filename)
        except GitCommandError as e:
            logger.warning(f"Error getting modified files: {e}")

        return modified_files

    def get_previous_commit_hash(self, commit_hash: str) -> Optional[str]:
        """
        Get the previous commit hash for a given commit.
        
        Args:
            commit_hash: Hash of the commit to get the previous commit for
            
        Returns:
            Previous commit hash as string, or None if it's the first commit
        """
        repo = self.shadow_git_repository
        if not repo:
            raise RuntimeError("Repository not initialized")

        try:
            # Use git to get the parent commit hash
            # git rev-parse commit_hash^1 gets the first parent of the commit
            parent_hash = repo.git.rev_parse(f"{commit_hash}^1")
            return parent_hash.strip()
        except (GitCommandError, BadName) as e:
            # This could mean it's the first commit (no parent) or invalid commit hash
            logger.warning(f"Could not get previous commit for {commit_hash}: {e}")
            return None


class GitServiceError(Exception):
    """Exception raised by GitService operations."""
    pass
