#!/usr/bin/env python3
"""
Test script for banner display functionality.

Usage:
    python test_banner.py [--pretty|--plain|--both]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path so we can import siada modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from siada.io.banner import show_siada_banner, get_banner_text
from rich.console import Console


def test_pretty_banner():
    """Test colorful banner with gradient."""
    print("=== PRETTY BANNER (Left-to-Right Gradient) ===")
    show_siada_banner(pretty=True)
    print()


def test_plain_banner():
    """Test plain text banner."""
    print("=== PLAIN BANNER ===")
    show_siada_banner(pretty=False)
    print()


def test_text_banner():
    """Test banner as string."""
    print("=== BANNER AS TEXT ===")
    print(get_banner_text())


def main():
    parser = argparse.ArgumentParser(description="Test SIADA HUB banner display")
    parser.add_argument("--pretty", action="store_true", help="Show only pretty banner")
    parser.add_argument("--plain", action="store_true", help="Show only plain banner")
    parser.add_argument("--both", action="store_true", help="Show both versions")
    
    args = parser.parse_args()
    
    if args.pretty:
        test_pretty_banner()
    elif args.plain:
        test_plain_banner()
    elif args.both:
        test_pretty_banner()
        test_plain_banner()
        test_text_banner()
    else:
        # Default: show all versions
        test_pretty_banner()
        test_plain_banner()
        test_text_banner()


if __name__ == "__main__":
    main() 