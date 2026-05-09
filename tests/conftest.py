"""
Pytest-fælles fixtures.

Vi tilføjer projektets rod til sys.path så imports som `from
anonymisering_pdf import ...` virker uden at skulle installere
projektet som en pip-pakke.
"""
import sys
from pathlib import Path

_ROD = Path(__file__).resolve().parent.parent
if str(_ROD) not in sys.path:
    sys.path.insert(0, str(_ROD))
