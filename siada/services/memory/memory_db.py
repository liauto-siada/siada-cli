"""
Memory Database Module

Provides SQLite database management with FTS5 full-text search capabilities.
Table structure is fully compatible with OpenClaw's memory implementation.
Enhanced with Chinese word segmentation for FTS5 indexing.
"""

import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from siada.foundation.logging import logger

# Import jieba for Chinese word segmentation (required dependency)
# Suppress the pkg_resources deprecation warning emitted by jieba._compat on import;
# this is a jieba internal issue and not actionable from our side.
import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba

# Global constant for chunk size and snippet truncation
DEFAULT_CHUNK_SIZE = 2048


@dataclass
class TextChunk:
    """Represents a chunk of text from a markdown file."""
    start_line: int
    end_line: int
    text: str
    hash: str


class MemoryDatabase:
    """
    Memory database manager with FTS5 full-text search support.
    
    Table structure is fully compatible with OpenClaw's implementation.
    """
    
    def __init__(self, db_path: Optional[Path] = None, enable_chinese: bool = True):
        """
        Initialize the memory database.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ~/.siada-cli/workspace/memory/memory.db
            enable_chinese: Enable Chinese word segmentation for FTS5 (default: True)
        """
        if db_path is None:
            memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            db_path = memory_dir / "memory.db"
        
        self.db_path = Path(db_path)
        self.memory_dir = self.db_path.parent  # Store memory directory for path resolution
        self.conn: Optional[sqlite3.Connection] = None
        self.fts_available = False
        self.fts_error: Optional[str] = None
        self.enable_chinese = enable_chinese
        
        # Initialize jieba (suppress loading messages)
        if self.enable_chinese:
            import logging as _logging
            jieba.setLogLevel(_logging.WARNING)
        
        # Initialize database and schema
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection and create schema."""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            
            # Create schema
            self._create_schema()
            
            logger.info(f"[memory-db] Database initialized at {self.db_path}")
            logger.info(f"[memory-db] FTS5 available: {self.fts_available}")
            
        except Exception as e:
            logger.error(f"[memory-db] Failed to initialize database: {e}")
            raise
    
    def _create_schema(self):
        """
        Create database schema compatible with OpenClaw.
        
        Tables:
        - meta: Metadata storage
        - files: Indexed file tracking
        - chunks: Text chunks with embeddings
        - chunks_fts: FTS5 full-text search index
        """
        cursor = self.conn.cursor()
        
        # Create meta table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Create files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'memory',
                hash TEXT NOT NULL,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL
            )
        """)
        
        # Create chunks table (compatible with OpenClaw)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'memory',
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                hash TEXT NOT NULL,
                model TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        
        # Create indexes for chunks
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)
        """)
        
        # Try to create FTS5 virtual table
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text,
                    id UNINDEXED,
                    path UNINDEXED,
                    source UNINDEXED,
                    model UNINDEXED,
                    start_line UNINDEXED,
                    end_line UNINDEXED
                )
            """)
            self.fts_available = True
            logger.info("[memory-db] FTS5 virtual table created successfully")
        except sqlite3.OperationalError as e:
            self.fts_available = False
            self.fts_error = str(e)
            logger.warning(f"[memory-db] FTS5 not available: {e}")
        
        self.conn.commit()
    
    def chunk_markdown(
        self, 
        content: str, 
        chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> List[TextChunk]:
        """
        Split markdown content into chunks by effective character count.
        
        Chunks are created based on the count of non-whitespace characters only,
        but the original text format (including all spaces, tabs, and newlines)
        is preserved in the chunk. This ensures uniform information density across
        chunks, which is especially important for code-heavy documents.
        
        Args:
            content: Markdown file content
            chunk_size: Maximum effective characters per chunk (default: DEFAULT_CHUNK_SIZE)
                       Whitespace (spaces, tabs, newlines) does not count toward this limit.
            
        Returns:
            List of TextChunk objects with preserved formatting
        """
        lines = content.split('\n')
        chunks: List[TextChunk] = []
        
        current_lines: List[str] = []
        current_effective_chars = 0  # Count only non-whitespace characters
        start_line = 1
        
        for i, line in enumerate(lines, start=1):
            # Calculate effective character count (excluding spaces and tabs)
            # Newlines are also not counted as they are formatting characters
            effective_length = len(line.replace(' ', '').replace('\t', ''))
            
            # If adding this line would exceed chunk size and we have content
            if current_effective_chars + effective_length > chunk_size and current_lines:
                # Create chunk from accumulated lines (preserving original format)
                chunk_text = '\n'.join(current_lines)
                chunk_hash = self._hash_text(chunk_text)
                
                chunks.append(TextChunk(
                    start_line=start_line,
                    end_line=i - 1,
                    text=chunk_text,
                    hash=chunk_hash
                ))
                
                # Start new chunk
                current_lines = [line]
                current_effective_chars = effective_length
                start_line = i
            else:
                current_lines.append(line)
                current_effective_chars += effective_length
        
        # Add remaining lines as final chunk
        if current_lines:
            chunk_text = '\n'.join(current_lines)
            chunk_hash = self._hash_text(chunk_text)
            
            chunks.append(TextChunk(
                start_line=start_line,
                end_line=len(lines),
                text=chunk_text,
                hash=chunk_hash
            ))
        
        logger.debug(f"[memory-db] Split content into {len(chunks)} chunks")
        return chunks
    
    def index_file(
        self,
        file_path: Path,
        source: str = 'memory',
        model: str = 'none'
    ) -> bool:
        """
        Index a markdown file into the database.
        
        Args:
            file_path: Path to markdown file (can be relative to memory_dir or absolute)
            source: Source type (default: 'memory')
            model: Model identifier (default: 'none')
            
        Returns:
            True if indexing succeeded, False otherwise
        """
        try:
            # Convert to Path if it's not already
            file_path = Path(file_path)
            
            # Determine if path is relative or absolute
            if file_path.is_absolute():
                # Use absolute path directly
                absolute_path = file_path
                # Try to get relative path for storage
                try:
                    stored_path = file_path.relative_to(self.memory_dir)
                except ValueError:
                    # If not under memory_dir, store absolute path
                    stored_path = file_path
            else:
                # Relative path - resolve relative to memory_dir
                absolute_path = self.memory_dir / file_path
                stored_path = file_path
            
            if not absolute_path.exists():
                logger.warning(f"[memory-db] File not found: {absolute_path}")
                return False
            
            # Read file content using absolute path
            content = absolute_path.read_text(encoding='utf-8')
            
            # Get file metadata using absolute path
            stat = absolute_path.stat()
            file_hash = self._hash_text(content)
            mtime_ms = int(stat.st_mtime * 1000)
            size = stat.st_size
            
            # Chunk the content
            chunks = self.chunk_markdown(content)
            
            if not chunks:
                logger.warning(f"[memory-db] No chunks generated for {stored_path}")
                return False
            
            # Get current timestamp
            now = int(datetime.now().timestamp() * 1000)
            
            cursor = self.conn.cursor()
            
            # Delete old chunks for this file (using stored_path)
            cursor.execute("DELETE FROM chunks WHERE path = ?", (str(stored_path),))
            if self.fts_available:
                cursor.execute("DELETE FROM chunks_fts WHERE path = ?", (str(stored_path),))
            
            # Insert new chunks
            for chunk in chunks:
                chunk_id = self._generate_chunk_id(
                    source=source,
                    path=str(stored_path),
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    chunk_hash=chunk.hash,
                    model=model
                )
                
                # Insert into chunks table
                cursor.execute("""
                    INSERT INTO chunks (
                        id, path, source, start_line, end_line, 
                        hash, model, text, embedding, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        hash=excluded.hash,
                        model=excluded.model,
                        text=excluded.text,
                        embedding=excluded.embedding,
                        updated_at=excluded.updated_at
                """, (
                    chunk_id,
                    str(stored_path),
                    source,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.hash,
                    model,
                    chunk.text,
                    "[]",  # Empty embedding for now
                    now
                ))
                
                # Insert into FTS5 table if available
                if self.fts_available:
                    # Preprocess text for FTS5 (segment Chinese if enabled)
                    fts_text = self._prepare_text_for_fts(chunk.text)
                    
                    cursor.execute("""
                        INSERT INTO chunks_fts (
                            text, id, path, source, model, start_line, end_line
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        fts_text,
                        chunk_id,
                        str(stored_path),
                        source,
                        model,
                        chunk.start_line,
                        chunk.end_line
                    ))
            
            # Update files table (using stored_path)
            cursor.execute("""
                INSERT INTO files (path, source, hash, mtime, size)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    source=excluded.source,
                    hash=excluded.hash,
                    mtime=excluded.mtime,
                    size=excluded.size
            """, (str(stored_path), source, file_hash, mtime_ms, size))
            
            self.conn.commit()
            
            logger.info(f"[memory-db] Indexed {len(chunks)} chunks from {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"[memory-db] Failed to index file {file_path}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def _generate_chunk_id(
        self,
        source: str,
        path: str,
        start_line: int,
        end_line: int,
        chunk_hash: str,
        model: str
    ) -> str:
        """
        Generate a unique chunk ID.
        
        Format matches OpenClaw: source:path:start:end:hash:model
        """
        composite = f"{source}:{path}:{start_line}:{end_line}:{chunk_hash}:{model}"
        return self._hash_text(composite)
    
    def _prepare_text_for_fts(self, text: str) -> str:
        """
        Prepare text for FTS5 indexing.
        
        If Chinese support is enabled, segments the text using jieba
        and joins with spaces so FTS5 can properly index Chinese words.
        
        Args:
            text: Original text
            
        Returns:
            Preprocessed text suitable for FTS5 indexing
        """
        if not self.enable_chinese:
            return text
        
        try:
            # Segment text using jieba
            words = jieba.cut(text)
            # Join with spaces for FTS5
            segmented = ' '.join(words)
            return segmented
        except Exception as e:
            logger.warning(f"[memory-db] Failed to segment text: {e}")
            return text
    
    def _hash_text(self, text: str) -> str:
        """Generate SHA256 hash of text."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def delete_file_records(self, file_path: str) -> bool:
        """
        Delete all database records for a file (from files, chunks, and chunks_fts tables).
        
        Args:
            file_path: File path (relative to memory_dir or absolute)
        
        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            file_path = Path(file_path)
            
            # Determine stored path (same logic as index_file)
            if file_path.is_absolute():
                try:
                    stored_path = file_path.relative_to(self.memory_dir)
                except ValueError:
                    stored_path = file_path
            else:
                stored_path = file_path
            
            cursor = self.conn.cursor()
            
            # Delete from chunks table
            cursor.execute("DELETE FROM chunks WHERE path = ?", (str(stored_path),))
            chunks_deleted = cursor.rowcount
            
            # Delete from chunks_fts table if available
            if self.fts_available:
                cursor.execute("DELETE FROM chunks_fts WHERE path = ?", (str(stored_path),))
            
            # Delete from files table
            cursor.execute("DELETE FROM files WHERE path = ?", (str(stored_path),))
            files_deleted = cursor.rowcount
            
            self.conn.commit()
            
            if chunks_deleted > 0 or files_deleted > 0:
                logger.info(f"[memory-db] Deleted records for {stored_path}: {chunks_deleted} chunks, {files_deleted} file entry")
            
            return True
            
        except Exception as e:
            logger.error(f"[memory-db] Failed to delete records for {file_path}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("[memory-db] Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
