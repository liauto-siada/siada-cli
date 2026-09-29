"""
siada/services/skills/manager.py
Skill manager - cached skill lifecycle management
"""

import threading
from pathlib import Path
from typing import Optional

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger
from .models import SkillLoadOutcome, SkillMetadata, SkillScope, SkillUsageProfile
from .loader import load_skills_from_roots
from .config import get_skill_roots
from .renderer import render_skills_section
from .seeder import build_seed_aware_scope_resolver, seed_if_version_changed



class SkillsManager:
    """
    Skill manager - Global singleton with stateless cwd design.
    
    Features:
    - Global singleton pattern (no initialization with cwd required)
    - cwd is passed as parameter to get_skills() method
    - siada_home defaults to ~/.siada-cli
    - Thread safe with caching by cwd
    - Supports force refresh
    """
    
    _instance: Optional["SkillsManager"] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton implementation"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    cls._instance = instance
        return cls._instance
    
    def __init__(self, siada_home: Optional[Path] = None):
        """
        Initialize SkillsManager singleton.
        
        Args:
            siada_home: Optional siada home directory, defaults to ~/.siada-cli
        """
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._initialized = True
        self._siada_home: Path = siada_home or SIADA_HOME
        self._cache: dict[Path, SkillLoadOutcome] = {}
        # Roots used at load time, kept alongside the outcome so prompt
        # rendering can alias skill paths without rescanning the filesystem
        self._roots_cache: dict[Path, dict[SkillScope, list[Path]]] = {}
        self._cache_lock = threading.Lock()

        # Sync built-in (SYSTEM) skills into the user skills dir, but ONLY
        # when the installed siada-cli version differs from the version
        # recorded in the seed manifest. Steady-state startups skip this
        # entirely, so neither prompt building nor skill execution ever
        # touches siada/resources/skills/. See seeder.py for full details.
        try:
            seed_if_version_changed(self._siada_home)
        except Exception as e:
            logger.warning(f"Failed to sync built-in skills: {e}")

        logger.debug(f"SkillsManager initialized with siada_home: {self._siada_home}")
    
    @classmethod
    def get_instance(cls) -> "SkillsManager":
        """
        Get or create the singleton instance.
        
        Returns:
            The SkillsManager singleton instance
        """
        if cls._instance is None:
            cls()  # Create instance with default siada_home
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton (mainly for testing)"""
        with cls._instance_lock:
            cls._instance = None
    
    def get_skills(self, cwd: Path, force_reload: bool = False) -> SkillLoadOutcome:
        """
        Get skills for the given cwd.
        
        Args:
            cwd: Current working directory (workspace)
            force_reload: Whether to force reload (ignore cache)
        
        Returns:
            Skill loading result
        """
        cwd = Path(cwd).resolve()
        
        # Check cache
        if not force_reload:
            with self._cache_lock:
                if cwd in self._cache:
                    logger.debug(f"Cache hit for cwd: {cwd}")
                    return self._cache[cwd]
        
        # Load skills. We skip the SYSTEM root here because built-in skills
        # are seeded into the USER root on version bumps and will be picked
        # up there, then re-tagged as SYSTEM by the seed-aware resolver
        # whenever they remain bit-for-bit identical to what was seeded.
        # Scanning resources/skills/ at runtime would only produce duplicates
        # that get shadowed during dedup.
        logger.info(f"Loading skills for cwd: {cwd}")
        roots = get_skill_roots(cwd, self._siada_home, include_system=False)
        scope_resolver = build_seed_aware_scope_resolver(self._siada_home)
        outcome = load_skills_from_roots(roots, scope_resolver=scope_resolver)

        # Update cache
        with self._cache_lock:
            self._cache[cwd] = outcome
            self._roots_cache[cwd] = roots
        
        logger.info(
            f"Loaded {len(outcome.skills)} skills "
            f"({len(outcome.errors)} errors) for cwd: {cwd}"
        )
        
        return outcome

    def skills_for_cwd(
        self, cwd: Path, force_reload: bool = False
    ) -> SkillLoadOutcome:
        """Compatibility alias for the original public skills lookup API.

        ``get_skills`` is the canonical method used by the new renderer, but
        integrations that cache results per working directory still call this
        older name.  Keep both paths on the same cache and loading semantics.
        """
        return self.get_skills(cwd, force_reload=force_reload)
    
    def invalidate_cache(self, cwd: Optional[Path] = None):
        """
        Invalidate cache for the specified cwd, or all cwd if not specified.
        
        Args:
            cwd: Optional cwd to invalidate cache for. If None, invalidates all cache.
        """
        with self._cache_lock:
            if cwd:
                cwd = Path(cwd).resolve()
                if cwd in self._cache:
                    del self._cache[cwd]
                    self._roots_cache.pop(cwd, None)
                    logger.debug(f"Skill cache invalidated for cwd: {cwd}")
            else:
                self._cache.clear()
                self._roots_cache.clear()
                logger.debug("All skill cache invalidated")
    
    def get_skill_by_name(self, cwd: Path, name: str) -> Optional[SkillMetadata]:
        """
        Get single skill by name.
        
        Args:
            cwd: Current working directory
            name: Skill name
        
        Returns:
            Matching SkillMetadata, or None if not found
        """
        outcome = self.get_skills(cwd)
        for skill in outcome.skills:
            if skill.name.lower() == name.lower():
                return skill
        return None
    
    def list_skill_names(self, cwd: Path) -> list[str]:
        """
        Get all available skill names for the given cwd.
        
        Args:
            cwd: Current working directory
            
        Returns:
            List of skill names
        """
        outcome = self.get_skills(cwd)
        return [skill.name for skill in outcome.skills]
    
    def get_skills_section(
        self,
        cwd: Path,
        include_empty_hint: bool = False,
        context_window: Optional[int] = None,
        activated_skill_names: Optional[set[str]] = None,
        usage_profile: SkillUsageProfile = SkillUsageProfile.STRICT,
    ) -> Optional[str]:
        """
        Get pre-rendered skills section for system prompt.
        
        Args:
            cwd: Current working directory
            include_empty_hint: Whether to include hint when no skills available
            context_window: Model context window in tokens, used to size the
                skill list budget (2% of the window). When None, a flat
                fallback budget applies.
            usage_profile: Instructions paired with the skills catalog.
        
        Returns:
            Rendered skills section string, or None if no skills
        """
        cwd = Path(cwd).resolve()
        outcome = self.get_skills(cwd)
        with self._cache_lock:
            roots = self._roots_cache.get(cwd)
        return render_skills_section(
            outcome.skills,
            include_empty_hint,
            skill_roots=roots,
            context_window=context_window,
            activated_skill_names=activated_skill_names,
            usage_profile=usage_profile,
        )
