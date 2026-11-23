"""Versionsbundna interna leveranser i simulatorns lokala rapportregister."""

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime

from reporting.premium_statement import DAYS, amount, collect
from simulation.premium_opening import DB
from utils.checksums import canonical_hash

RUN = re.compile("[0-9a-f]{32}")
STATUSES = {"pending": "Väntar på granskning", "returned": "Återremitterad",
            "approved": "Godkänd, väntar på kvitto", "received": "Mottagen"}
SCHEMA = """CREATE TABLE IF NOT EXISTS deliveries (
    report TEXT NOT NULL, rev INTEGER NOT NULL, digest TEXT NOT NULL UNIQUE,
    packet TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL,
    decision TEXT, receipt TEXT, PRIMARY KEY (report, rev))"""


def now():
    return datetime.now(UTC).isoformat()


def identity(run, day):
    if not RUN.fullmatch(run) or day not in DAYS:
        raise ValueError("Ogiltig rapportidentitet")
    return f"V12-{run}-{day}"


def encode(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


class PremiumDeliveries:
    def __init__(self, root):
        self.root = root
        self.path = root / "v12.sqlite"

    @contextmanager
    def connection(self, write=False):
        with closing(sqlite3.connect(self.path, timeout=12)) as db, db:
            db.row_factory = sqlite3.Row
            if write:
                db.execute(SCHEMA)
                db.execute("BEGIN IMMEDIATE")
            yield db

    def sources(self):
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if RUN.fullmatch(p.name) and (p / DB).is_file() and p.resolve() == p)

    def listing(self):
        if not self.path.is_file():
            return []
        with self.connection() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='deliveries'").fetchone():
                return []
            return [dict(row) for row in db.execute(
                "SELECT report, rev, status, digest, rev = max(rev) OVER (PARTITION BY report) AS latest "
                "FROM deliveries ORDER BY rowid DESC")]

    @staticmethod
    def _record(row):
        if row is None:
            raise ValueError("Rapportversionen finns inte")
        data = dict(row)
        for key in ("packet", "decision", "receipt"):
            data[key] = json.loads(data[key]) if data[key] else None
        packet = data["packet"]
        if (canonical_hash(packet) != data["digest"] or packet["id"] != data["report"]
                or packet["revision"] != data["rev"]):
            raise ValueError("Rapportversionens kontrollsumma avviker")
        return data

    def get(self, ident, rev, *, specialist=False):
        if not self.path.is_file():
            raise ValueError("Rapportversionen finns inte")
        with self.connection() as db:
            row = db.execute("SELECT * FROM deliveries WHERE report=? AND rev=?", (ident, rev)).fetchone()
            record = self._record(row)
            record["latest"] = db.execute("SELECT max(rev) FROM deliveries WHERE report=?", (ident,)).fetchone()[0] == rev
            evidence = record.pop("evidence")
            if specialist:
                record["evidence"] = json.loads(evidence)
                if canonical_hash(record["evidence"]) != record["packet"]["evidence_hash"]:
                    raise ValueError("Specialistunderlagets kontrollsumma avviker")
            return record

    def prepare(self, run, day, actor, *, previous="", reason="", source_run=""):
        ident = identity(run, day)
        reason = reason.strip()
        if bool(previous) != bool(reason) or len(reason) > 1000 or (not previous and source_run):
            raise ValueError("En rättelse kräver föregående leveranssumma och en kort orsak")
        source_run = source_run or run
        identity(source_run, day)
        if not (self.root / source_run / DB).is_file():
            raise ValueError("Körningens lokala SQLite-fil saknas")
        with self.connection(write=True) as db:
            row = db.execute("SELECT * FROM deliveries WHERE report=? ORDER BY rev DESC LIMIT 1", (ident,)).fetchone()
            prior = self._record(row) if row else None
            if prior and not previous:
                return prior["rev"]
            if previous and (not prior or prior["digest"] != previous or prior["status"] == "pending"):
                raise ValueError("Rättelsen kräver den senaste beslutade versionen")
            parent = prior
            if day == DAYS[1] and not previous:
                original = db.execute("SELECT * FROM deliveries WHERE report=? ORDER BY rev DESC LIMIT 1",
                                      (identity(run, DAYS[0]),)).fetchone()
                if not original or original["status"] not in ("approved", "received"):
                    raise ValueError("Godkänn novemberrapporten före den daterade uppföljningen")
                parent = self._record(original)
                source_run = parent["packet"]["source_run"]
            summary, evidence, failures = collect(self.root, source_run, day)
            delta = {}
            rev = 1
            if prior:
                old = prior["packet"]["summary"]
                if old["scenario"] != summary["scenario"]:
                    raise ValueError("Rättelsen måste avse samma scenario")
                delta = {k: format(amount(v) - amount(old["amounts"][k]), ".2f")
                         if k in old["amounts"] else "Tidigare värde saknas" for k, v in summary["amounts"].items()}
                rev = prior["rev"] + 1
            packet = {"contract": "V-12 1.0", "id": ident, "revision": rev, "source_run": source_run,
                      "type": "Rättelse" if previous else ("Ordinarie rapport" if day == DAYS[0] else "Daterad uppföljning"),
                      "producer": actor, "prepared_at": now(), "parent": parent["digest"] if parent else "",
                      "parent_id": parent["report"] if parent else None, "parent_rev": parent["rev"] if parent else None,
                      "reason": reason, "delta": delta,
                      "summary": summary, "failures": failures, "evidence_hash": canonical_hash(evidence)}
            db.execute("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL)",
                       (ident, rev, canonical_hash(packet), encode(packet), encode(evidence)))
            return rev

    def act(self, ident, rev, digest, action, actor, reason=""):
        if not self.path.is_file():
            raise ValueError("Rapportversionen finns inte")
        with self.connection(write=True) as db:
            row = db.execute("SELECT * FROM deliveries WHERE report=? AND rev=?", (ident, rev)).fetchone()
            record = self._record(row)
            if digest != record["digest"]:
                raise ValueError("Leveranssumman avviker. Öppna versionen igen.")
            if action == "receive" and record["receipt"]:
                return
            latest = db.execute("SELECT max(rev) FROM deliveries WHERE report=?", (ident,)).fetchone()[0]
            if latest != rev:
                raise ValueError("En senare revision finns")
            audit = {"report": ident, "revision": rev, "digest": digest, "actor": actor, "at": now()}
            if action == "receive":
                if record["status"] != "approved":
                    raise ValueError("Kvittens kräver en godkänd rapportversion")
                db.execute("UPDATE deliveries SET receipt=?, status='received' WHERE report=? AND rev=?",
                           (encode(audit), ident, rev))
                return
            if action not in ("approve", "return") or record["status"] != "pending":
                raise ValueError("Versionen väntar inte på detta beslut")
            if not reason.strip() or len(reason) > 1000:
                raise ValueError("Ange en motivering på högst 1 000 tecken")
            if action == "approve" and (record["packet"]["failures"] or
                    canonical_hash(json.loads(record["evidence"])) != record["packet"]["evidence_hash"]):
                raise ValueError("Kontrollfel blockerar godkännande")
            verdict = "approved" if action == "approve" else "returned"
            audit.update(verdict=verdict, reason=reason.strip())
            db.execute("UPDATE deliveries SET decision=?, status=? WHERE report=? AND rev=?",
                       (encode(audit), verdict, ident, rev))
