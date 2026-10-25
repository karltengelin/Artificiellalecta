"""UUID-kolumner i SQLite (demo- och testdatabaserna, models/base.py).

Typnamnet UUID ger NUMERIC-affinitet i SQLite. En slumpad uuid4 vars hexform bara har
siffror (eller siffror med ett 'e') lagrades då som tal: ungefär en gång på en miljon,
vilket i helkörningen gav ett enstaka ERROR vid uppsättningen av demobeståndet.
Här prövas sådana värden uttryckligen i stället för att vänta på slumpen.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from models import Base, Employer, InsuredPerson
from services.db import session_factory_for

# Hexformer som SQLite med NUMERIC-affinitet gör om till INTEGER/REAL
NUMERIC_LOOKING = [
    "61691214925247470000000000000000",  # bara siffror – för stort för INTEGER, blir REAL
    "00000000000000000000000000000001",  # inledande nollor försvinner som tal
    "123456789012345678901234567e1234",  # siffror, 'e' och siffror – läses som exponent
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield session_factory_for(engine)
    engine.dispose()


def add_employer(session_factory, employer_id: uuid.UUID, org_number: str) -> None:
    with session_factory() as s:
        s.add(Employer(id=employer_id, org_number=org_number, name="Testbolaget AB",
                       affiliation_date=date(2010, 1, 1)))


@pytest.mark.parametrize("hex_value", NUMERIC_LOOKING)
def test_uuid_som_ser_ut_som_tal_lagras_som_text_och_lases_tillbaka(db, hex_value):
    employer_id = uuid.UUID(hex_value)
    add_employer(db, employer_id, "5560000001")
    with db() as s:
        assert s.execute(text("SELECT typeof(id), id FROM employers")).one() == ("text", hex_value)
        assert s.scalar(select(Employer.id)) == employer_id
        assert s.get(Employer, employer_id).org_number == "5560000001"


def test_flerradsinsert_med_sentinel_klarar_uuid_som_ser_ut_som_tal(db):
    # Demobeståndet skrivs med insertmanyvalues: SQLAlchemy läser tillbaka primärnyckeln
    # som sentinel per rad – det var där felet syntes ("'float' object has no attribute 'replace'")
    ids = [uuid.UUID(h) for h in NUMERIC_LOOKING]
    with db() as s:
        employer = Employer(org_number="5560000001", name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
        s.add(employer)
        s.flush()
        s.add_all(
            InsuredPerson(id=person_id, personal_id_number=f"19900101{number:04d}", first_name="Test",
                          last_name="Testsson", employer_id=employer.id, employment_start_date=date(2015, 1, 1),
                          status="active")
            for number, person_id in enumerate(ids)
        )
    with db() as s:
        assert set(s.scalars(select(InsuredPerson.id))) == set(ids)


def test_postgres_behaller_sin_uuid_typ():
    ddl = str(CreateTable(Employer.__table__).compile(dialect=postgresql.dialect()))
    assert "id UUID NOT NULL" in ddl
