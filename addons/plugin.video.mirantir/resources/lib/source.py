# -*- coding: utf-8 -*-
"""Mirantir catalogue API used by the Kodi router and background service.

Keep user-facing calls simple; repository discovery and SQLite lifecycle
are isolated in their own modules for easier testing and maintenance.
"""

from palantir_source import discover, load_state
from catalogue_sync import sync, update_required

__all__ = ["discover", "load_state", "sync", "update_required"]
