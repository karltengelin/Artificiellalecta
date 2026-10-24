"""Bygg den fiktiva exempelrapporten om agentnyttjande i Digital klarhet.

Kräver reportlab och lokala DM Sans-TTF-filer. Ingen databas eller AI anropas.
Se 06_design/exempel/README.md för underlag och körinstruktion.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reporting.agent_usage_example import main

if __name__ == "__main__":
    main()
