#!/usr/bin/env python3
"""
VicnovaLabs Squad Engine — Triage & Orchestration Entrypoint (jev_triage).
Provides backward compatibility and seamless invocation for IDE commands and scripts.
"""

import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from squad_engine.cli import main

if __name__ == "__main__":
    main()
