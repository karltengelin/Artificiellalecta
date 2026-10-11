"""Tjänstelagrets operationer – registreras i standardregistret när paketet importeras.

Vad agenter får göra med dem står i services/access_register.yaml.
"""

from services.operations import corrections, insured, policies, premiums, salary  # noqa: F401
