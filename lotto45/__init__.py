"""Lotto 6 aus 45 – Datenarchiv. Copyright Josef Lehner, GPL-3.0-only."""
VERSION = '1.0.23'

from pathlib import Path
import sys
_vendor=Path(__file__).resolve().parent.parent/'vendor'
if _vendor.is_dir():sys.path.insert(0,str(_vendor))
