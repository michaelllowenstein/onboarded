#!/usr/bin/env python3
"""
ef_snapshot.py — derive tenant schema data from an EF Core model snapshot.

EF Core keeps `<DbContext>ModelSnapshot.cs` in a project's Migrations folder:
the model as every migration applied in order produces it. Reading it gives
onboarded exact table/column/type/nullability facts without running the app,
the SDK or a database.

    ef_snapshot.py SNAPSHOT.cs profiles [--schema public] [--tables A,B]
        → JSON for domain.json "schema": {"public.Table": [{"name","type","nullable"}, …]}
    ef_snapshot.py SNAPSHOT.cs ddl [--schema public] [--tables A,B]
        → Postgres DDL (top-level columns, primary keys, foreign keys) for local rehearsal

Scope: top-level entity properties, keys and relationships. Owned types
(OwnsOne/OwnsMany, stored as extra columns or side tables) are listed as a
comment, not reproduced — use the project's own `dotnet ef database update`
for the full schema. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENTITY = re.compile(r'^\s{12}modelBuilder\.Entity\("([\w.]+)", b =>\s*$')
PROP = re.compile(r'^\s+b\.Property<([\w?.<>\[\]]+)>\("(\w+)"\)')
COLTYPE = re.compile(r'\.HasColumnType\("([^"]+)"\)')
TOTABLE = re.compile(r'^\s+b\.ToTable\("(\w+)"\)')
HASKEY = re.compile(r'^\s+b\.HasKey\(([^)]*)\)')
HASONE = re.compile(r'^\s+b\.HasOne\("([\w.]+)"')
FKEY = re.compile(r'\.HasForeignKey\("(\w+)"\)')
ONDELETE = re.compile(r'\.OnDelete\(DeleteBehavior\.(\w+)\)')
OWNS = re.compile(r'^\s+b\.Owns(One|Many)\("([\w.]+)", "(\w+)"')

VALUE_TYPES = {"int", "long", "short", "bool", "double", "float", "decimal", "DateTime", "DateTimeOffset",
               "Guid", "TimeSpan", "byte", "DateOnly", "TimeOnly"}
ON_DELETE_SQL = {"Cascade": "CASCADE", "Restrict": "RESTRICT", "SetNull": "SET NULL", "NoAction": "NO ACTION",
                 "ClientSetNull": "NO ACTION"}


def parse(path: Path) -> dict:
    """{entity: {"table", "props": [(name, clr, coltype, required)], "key": [...], "fks": [...], "owned": [...]}}"""
    lines = path.read_text(encoding="utf-8").splitlines()
    entities: dict[str, dict] = {}
    cur = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = ENTITY.match(line)
        if m:
            cur = entities.setdefault(m.group(1), {"table": None, "props": [], "key": [], "fks": [], "owned": []})
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        if not line.strip() or line.strip() in ("{", "}", "});", "{;"):
            i += 1
            continue
        # gather one fluent statement (until the line ending with ';')
        stmt = [line]
        while not stmt[-1].rstrip().endswith(";") and i + 1 < len(lines) and not ENTITY.match(lines[i + 1]):
            i += 1
            stmt.append(lines[i])
        text = " ".join(s.strip() for s in stmt)
        first = stmt[0]
        if (m := PROP.match(first)) and first.startswith(" " * 20 + "b.Property"):
            clr, name = m.groups()
            ct = COLTYPE.search(text)
            required = ".IsRequired()" in text or (not clr.endswith("?") and clr in VALUE_TYPES)
            if not any(p[0] == name for p in cur["props"]):
                cur["props"].append((name, clr, ct.group(1) if ct else None, required))
        elif (m := TOTABLE.match(first)) and first.startswith(" " * 20 + "b.ToTable"):
            cur["table"] = cur["table"] or m.group(1)
        elif (m := HASKEY.match(first)) and first.startswith(" " * 20 + "b.HasKey"):
            cur["key"] = re.findall(r'"(\w+)"', m.group(1))
        elif (m := HASONE.match(first)) and first.startswith(" " * 20 + "b.HasOne"):
            fk = FKEY.search(text)
            if fk:
                od = ONDELETE.search(text)
                cur["fks"].append({"column": fk.group(1), "references": m.group(1),
                                   "on_delete": od.group(1) if od else "NoAction"})
        elif (m := OWNS.match(first)) and first.startswith(" " * 20 + "b.Owns"):
            cur["owned"].append(f"{m.group(3)} ({m.group(1).lower()} {m.group(2).rsplit('.', 1)[-1]})")
        i += 1
    for v in entities.values():            # primary-key columns are never nullable
        v["props"] = [(n, clr, ct, req or n in v["key"]) for n, clr, ct, req in v["props"]]
    return {k: v for k, v in entities.items() if v["table"]}


def _pick(ents: dict, tables: list[str] | None) -> list[tuple[str, dict]]:
    items = sorted(ents.items(), key=lambda kv: kv[1]["table"])
    if tables:
        want = {t.lower() for t in tables}
        items = [kv for kv in items if kv[1]["table"].lower() in want]
    return items


def profiles(ents: dict, schema: str, tables: list[str] | None) -> dict:
    out = {}
    for _, e in _pick(ents, tables):
        out[f"{schema}.{e['table']}"] = [
            {"name": n, "type": ct or clr.rstrip("?"), "nullable": not req} for n, clr, ct, req in e["props"]
        ]
    return out


def ddl(ents: dict, schema: str, tables: list[str] | None) -> str:
    q = lambda s: '"' + s.replace('"', '""') + '"'
    picked = _pick(ents, tables)
    names = {e for e, _ in picked}
    out = [f"-- Generated by ef_snapshot.py — top-level columns, keys and foreign keys only.",
           f"-- Owned types are not reproduced; the real schema comes from `dotnet ef database update`.",
           f"CREATE SCHEMA IF NOT EXISTS {q(schema)};", ""]
    for _, e in picked:
        cols = [f"    {q(n)} {ct or 'text'}{' NOT NULL' if req else ''}" for n, clr, ct, req in e["props"]]
        if e["key"]:
            cols.append(f"    PRIMARY KEY ({', '.join(q(k) for k in e['key'])})")
        if e["owned"]:
            out.append(f"-- {e['table']} also owns: {', '.join(e['owned'])}")
        out.append(f"CREATE TABLE IF NOT EXISTS {q(schema)}.{q(e['table'])} (\n" + ",\n".join(cols) + "\n);")
        out.append("")
    for ent, e in picked:
        for fk in e["fks"]:
            if fk["references"] not in names:
                continue
            ref = ents[fk["references"]]
            if not ref["key"]:
                continue
            cname = f"FK_{e['table']}_{ref['table']}_{fk['column']}"[:63]
            out.append(f"ALTER TABLE {q(schema)}.{q(e['table'])} DROP CONSTRAINT IF EXISTS {q(cname)};")
            out.append(f"ALTER TABLE {q(schema)}.{q(e['table'])} ADD CONSTRAINT {q(cname)} FOREIGN KEY ({q(fk['column'])}) "
                       f"REFERENCES {q(schema)}.{q(ref['table'])} ({q(ref['key'][0])}) "
                       f"ON DELETE {ON_DELETE_SQL.get(fk['on_delete'], 'NO ACTION')};")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("snapshot", type=Path)
    p.add_argument("what", choices=["profiles", "ddl", "tables"])
    p.add_argument("--schema", default="public")
    p.add_argument("--tables", help="comma-separated table names to include")
    a = p.parse_args(argv)
    ents = parse(a.snapshot)
    tables = [t.strip() for t in a.tables.split(",")] if a.tables else None
    if a.what == "tables":
        for _, e in _pick(ents, tables):
            print(f"{e['table']:24} {len(e['props']):3} columns  key={','.join(e['key'])}  fks={len(e['fks'])}"
                  + (f"  owns={len(e['owned'])}" if e["owned"] else ""))
    elif a.what == "profiles":
        print(json.dumps(profiles(ents, a.schema, tables), indent=2))
    else:
        sys.stdout.write(ddl(ents, a.schema, tables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
