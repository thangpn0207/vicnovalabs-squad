#!/usr/bin/env python3
"""
Backward-compatibility bridge for Antigravity Specialized Squad.
Forwards all calls directly to the sanitized squad_engine package.
"""

import sys
import os
from pathlib import Path

# Add repo root and current dir to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure squad_engine is importable
try:
    from squad_engine.cli import main
except ImportError:
    # If installed via pip or in different layout
    import site
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    from squad_engine.cli import main

if __name__ == "__main__":
    main()
