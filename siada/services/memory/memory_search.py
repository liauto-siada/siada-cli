"""
Memory Search Module

Provides full-text search capabilities using SQLite FTS5.
Search implementation is compatible with OpenClaw's approach,
with additional support for Chinese word segmentation using jieba.
"""

import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Set
from dataclasses import dataclass

from siada.foundation.logging import logger

# Import jieba for Chinese word segmentation (required dependency)
import jieba


@dataclass
class SearchResult:
    """Result from a memory search query."""
    id: str
    path: str
    source: str
    start_line: int
    end_line: int
    score: float
    snippet: str


class MemorySearch:
    """
    Memory search service using FTS5 full-text search.
    
    Provides keyword search with BM25 ranking, compatible with OpenClaw.
    Enhanced with Chinese word segmentation support using jieba.
    """
    
    # Default Chinese stopwords
    DEFAULT_CHINESE_STOPWORDS = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '那', '个', '们', '他', '她', '它', '啊', '吗', '呢', '吧', '哦'
    }
    
    def __init__(
        self, 
        db_path: Optional[Path] = None,
        enable_chinese: bool = True,
        custom_dict: Optional[List[str]] = None,
        stopwords: Optional[Set[str]] = None
    ):
        """
        Initialize the memory search service.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ~/.siada-cli/workspace/memory/memory.db
            enable_chinese: Enable Chinese word segmentation (default: True)
            custom_dict: Custom dictionary words to add to jieba (e.g., technical terms)
            stopwords: Custom stopwords set. If None, uses DEFAULT_CHINESE_STOPWORDS
        """
        if db_path is None:
            memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
            db_path = memory_dir / "memory.db"
        
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self.fts_available = False
        self.enable_chinese = enable_chinese
        
        # Setup stopwords
        self.stopwords = stopwords if stopwords is not None else self.DEFAULT_CHINESE_STOPWORDS.copy()
        
        # Initialize jieba if Chinese support is enabled
        if self.enable_chinese:
            self._init_jieba(custom_dict)
        
        # Initialize database connection
        self._init_connection()
    
    def _init_jieba(self, custom_dict: Optional[List[str]] = None):
        """
        Initialize jieba with custom dictionary.
        
        Args:
            custom_dict: List of custom words to add to jieba dictionary
        """
        try:
            # Suppress jieba's loading messages
            import logging as _logging
            jieba.setLogLevel(_logging.INFO)
            
            # Add common technical terms
            default_tech_terms = [
                'Python', 'FastAPI', 'Django', 'Flask', 'JavaScript', 'TypeScript',
                'React', 'Vue', 'Angular', 'Node.js', 'npm', 'yarn', 'webpack',
                'Docker', 'Kubernetes', 'Redis', 'MongoDB', 'PostgreSQL', 'MySQL',
                'API', 'REST', 'GraphQL', 'gRPC', 'WebSocket', 'HTTP', 'HTTPS',
                'async', 'await', 'Promise', 'callback', 'decorator', 'middleware',
                'frontend', 'backend', 'fullstack', 'DevOps', 'CI/CD', 'Git',
                'Linux', 'Ubuntu', 'CentOS', 'MacOS', 'Windows', 'VSCode', 'MindRT',
                'MindUI', 'MindOS'
            ]
            
            for term in default_tech_terms:
                jieba.add_word(term)
            
            # Add user custom dictionary
            if custom_dict:
                for word in custom_dict:
                    jieba.add_word(word)
                logger.debug(f"[memory-search] Added {len(custom_dict)} custom words to jieba")
            
            logger.info("[memory-search] jieba initialized with custom dictionary")
            
        except Exception as e:
            logger.error(f"[memory-search] Failed to initialize jieba: {e}")
            raise
    
    def _init_connection(self):
        """Initialize database connection and check FTS5 availability."""
        try:
            if not self.db_path.exists():
                logger.warning(f"[memory-search] Database not found: {self.db_path}")
                return
            
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            
            # Check if FTS5 table exists
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='chunks_fts'
            """)
            
            self.fts_available = cursor.fetchone() is not None
            
            logger.info(f"[memory-search] Search service initialized, FTS5 available: {self.fts_available}")
            
        except Exception as e:
            logger.error(f"[memory-search] Failed to initialize: {e}")
            self.fts_available = False
    
    def search(
        self,
        query: str,
        limit: int = 10,
        snippet_max_chars: int = 300,
        source_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Search memory using FTS5 full-text search.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            snippet_max_chars: Maximum characters in result snippet
            source_filter: Optional filter by source ('memory' or 'session')
            
        Returns:
            List of SearchResult objects sorted by relevance (BM25 score)
        """
        if not self.conn or not self.fts_available:
            logger.warning("[memory-search] Search not available (FTS5 not initialized)")
            return []
        
        if not query or not query.strip():
            logger.debug("[memory-search] Empty query")
            return []
        
        if limit <= 0:
            return []
        
        try:
            # Build FTS5 query
            fts_query = self._build_fts_query(query)
            
            if not fts_query:
                logger.debug("[memory-search] No valid FTS query generated")
                return []
            
            # Build SQL query
            sql = """
                SELECT 
                    id, path, source, start_line, end_line, text,
                    bm25(chunks_fts) AS rank
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
            """
            
            params = [fts_query]
            
            # Add source filter if specified
            if source_filter:
                sql += " AND source = ?"
                params.append(source_filter)
            
            sql += " ORDER BY rank ASC LIMIT ?"
            params.append(limit)
            
            # Execute query
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            
            rows = cursor.fetchall()
            
            # Convert to SearchResult objects
            results = []
            for row in rows:
                # Convert BM25 rank to score (lower rank = better match)
                score = self._bm25_rank_to_score(row['rank'])
                
                # Truncate snippet
                snippet = self._truncate_snippet(row['text'], snippet_max_chars)
                
                results.append(SearchResult(
                    id=row['id'],
                    path=row['path'],
                    source=row['source'],
                    start_line=row['start_line'],
                    end_line=row['end_line'],
                    score=score,
                    snippet=snippet
                ))
            
            logger.info(f"[memory-search] Found {len(results)} results for query: {query[:50]}")
            return results
            
        except Exception as e:
            logger.error(f"[memory-search] Search failed: {e}")
            return []
    
    def _build_fts_query(self, raw_query: str) -> Optional[str]:
        """
        Build FTS5 query from raw user input.
        
        Converts user query into FTS5 syntax using AND logic.
        Enhanced with Chinese word segmentation support.
        
        Args:
            raw_query: Raw user query string
            
        Returns:
            FTS5 query string, or None if no valid tokens
        """
        if self.enable_chinese:
            # Use jieba for Chinese + English mixed segmentation
            tokens = self._segment_with_jieba(raw_query)
        else:
            # Fallback to simple alphanumeric extraction (OpenClaw style)
            tokens = re.findall(r'[A-Za-z0-9_]+', raw_query)
            tokens = [t.strip() for t in tokens if t.strip()]
        
        if not tokens:
            return None
        
        # Quote each token and join with AND
        quoted_tokens = [f'"{token}"' for token in tokens]
        fts_query = ' OR '.join(quoted_tokens)
        
        logger.debug(f"[memory-search] Raw query: {raw_query}")
        logger.debug(f"[memory-search] Tokens: {tokens}")
        logger.debug(f"[memory-search] FTS query: {fts_query}")
        return fts_query
    
    def _segment_with_jieba(self, text: str) -> List[str]:
        """
        Segment text using jieba with filtering.
        
        Args:
            text: Input text to segment
            
        Returns:
            List of filtered tokens
        """
        # Use search mode for better recall
        tokens = jieba.cut_for_search(text)
        
        # Filter tokens
        filtered = []
        for token in tokens:
            token = token.strip()
            
            # Skip empty tokens
            if not token:
                continue
            
            # Skip single character tokens that are stopwords
            if len(token) == 1 and token in self.stopwords:
                continue
            
            # Skip pure punctuation
            if re.match(r'^[^\w]+$', token, re.UNICODE):
                continue
            
            # Keep tokens with at least 2 chars or alphanumeric
            if len(token) >= 2 or re.match(r'^[A-Za-z0-9_]+$', token):
                # Remove from stopwords if it's a multi-char token
                if token not in self.stopwords or len(token) > 2:
                    filtered.append(token)
        
        return filtered
    
    def _bm25_rank_to_score(self, rank: float) -> float:
        """
        Convert BM25 rank to normalized score.
        
        Compatible with OpenClaw's bm25RankToScore function.
        Lower rank values indicate better matches.
        
        Args:
            rank: BM25 rank value from FTS5
            
        Returns:
            Normalized score between 0 and 1
        """
        # Normalize rank to positive value
        normalized = max(0, rank) if rank is not None and isinstance(rank, (int, float)) else 999
        
        # Convert to score (higher is better)
        score = 1.0 / (1.0 + normalized)
        
        return score
    
    def _truncate_snippet(self, text: str, max_chars: int) -> str:
        """
        Truncate text to maximum characters safely.
        
        Args:
            text: Full text content
            max_chars: Maximum characters to return
            
        Returns:
            Truncated text
        """
        if len(text) <= max_chars:
            return text
        
        # Truncate and add ellipsis
        return text[:max_chars] + "..."
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("[memory-search] Connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
