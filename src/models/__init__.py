"""SQLAlchemy-modeller för operativa databasen.

Re-exporterar `Base` samt alla modeller så att t.ex. `Base.metadata.create_all`
ser samtliga tabeller. Lägg in nya modeller här när de skapas.
"""

from .base import Base
from .employer import Employer
from .insured_person import InsuredPerson

__all__ = ["Base", "Employer", "InsuredPerson"]
