"""
AST analysis data models and structures.
"""

from collections import namedtuple
from typing import Generator, Optional

# Tag namedtuple for representing code identifiers
Tag = namedtuple("Tag", "rel_fname fname line name kind".split())

__all__ = ["Tag"]
