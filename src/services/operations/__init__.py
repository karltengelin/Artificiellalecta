"""Tjänstelagrets operationer – registreras i standardregistret när paketet importeras.

Vad agenter får göra med dem står i services/access_register.yaml.
"""

from services.operations import (  # noqa: F401
    cases,
    corrections,
    employers,
    enrollment,
    insured,
    journal,
    persons,
    policies,
    premiums,
    salary,
)
