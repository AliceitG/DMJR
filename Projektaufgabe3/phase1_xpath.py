"""
XPath-Achsen auf dem EDGE-Modell.

Alle Berechnungen finden als SQL-Rekursion in der Datenbank statt.
Die Python-Funktionen dienen nur als Controller (Rekursion steuern,
SQL generieren, Ergebnis zurückgeben).

Korrektheitsprüfung (Toy-Beispiel):
  i.   ancestor      – alle Vorfahren von author "Daniel Ulrich Schmitt"
  ii.  descendant    – alle Nachkommen von Knoten vldb_2023
  iii. following/preceding-sibling – für SchmittKAMM23 und SchalerHS23
"""

import psycopg2

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}


# ---------------------------------------------------------------------------
# XPath-Achsen-Funktionen
# ---------------------------------------------------------------------------

def ancestor(conn, v_id: int) -> list[tuple]:
    """Alle Vorfahren-Knoten von v (ancestor-Achse)."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE anc AS (
                SELECT e."from" AS id
                FROM   edge e
                WHERE  e."to" = %s
                UNION ALL
                SELECT e."from"
                FROM   edge e
                JOIN   anc   a ON e."to" = a.id
            )
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node n
            JOIN   anc  a ON n.id = a.id
            ORDER  BY n.id
        """, (v_id,))
        return cur.fetchall()


def descendant(conn, v_id: int) -> list[tuple]:
    """Alle Nachkommen-Knoten von v (descendant-Achse)."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE desc_ AS (
                SELECT e."to" AS id
                FROM   edge e
                WHERE  e."from" = %s
                UNION ALL
                SELECT e."to"
                FROM   edge  e
                JOIN   desc_ d ON e."from" = d.id
            )
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node  n
            JOIN   desc_ d ON n.id = d.id
            ORDER  BY n.id
        """, (v_id,))
        return cur.fetchall()


def following_sibling(conn, v_id: int) -> list[tuple]:
    """Alle nachfolgenden Geschwister-Knoten von v (following-sibling-Achse).

    Dokumentreihenfolge wird durch aufsteigende node.id abgebildet,
    da Knoten in Baumreihenfolge (DFS) eingefügt werden.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH parent AS (
                SELECT e."from" AS parent_id
                FROM   edge e
                WHERE  e."to" = %s
            ),
            siblings AS (
                SELECT e."to" AS id
                FROM   edge   e
                JOIN   parent p ON e."from" = p.parent_id
                WHERE  e."to" > %s
            )
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node     n
            JOIN   siblings s ON n.id = s.id
            ORDER  BY n.id
        """, (v_id, v_id))
        return cur.fetchall()


def preceding_sibling(conn, v_id: int) -> list[tuple]:
    """Alle vorhergehenden Geschwister-Knoten von v (preceding-sibling-Achse)."""
    with conn.cursor() as cur:
        cur.execute("""
            WITH parent AS (
                SELECT e."from" AS parent_id
                FROM   edge e
                WHERE  e."to" = %s
            ),
            siblings AS (
                SELECT e."to" AS id
                FROM   edge   e
                JOIN   parent p ON e."from" = p.parent_id
                WHERE  e."to" < %s
            )
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node     n
            JOIN   siblings s ON n.id = s.id
            ORDER  BY n.id
        """, (v_id, v_id))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def find_node(conn, *, s_id: str = None, type_: str = None, content: str = None) -> list[tuple]:
    """Knoten anhand von Attributen suchen."""
    conditions, params = [], []
    if s_id is not None:
        conditions.append("s_id = %s");    params.append(s_id)
    if type_ is not None:
        conditions.append("type = %s");    params.append(type_)
    if content is not None:
        conditions.append("content = %s"); params.append(content)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, s_id, type, content FROM node WHERE {' AND '.join(conditions)}",
            params,
        )
        return cur.fetchall()


def _fmt(rows: list[tuple]) -> str:
    if not rows:
        return "  (keine Ergebnisse)"
    lines = []
    for id_, s_id, type_, content in rows:
        parts = [f"id={id_}", f"type={type_}"]
        if s_id:
            parts.append(f"s_id={s_id}")
        if content:
            parts.append(f"content={content}")
        lines.append("  " + ", ".join(parts))
    return "\n".join(lines)


def _print(label: str, rows: list[tuple]) -> None:
    print(f"\n--- {label} ---")
    print(_fmt(rows))


# ---------------------------------------------------------------------------
# Korrektheitsprüfung
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = psycopg2.connect(**db_config)

    # i. Ancestor-Knoten von author "Daniel Ulrich Schmitt"
    print("=== i. ancestor ===")
    hits = find_node(conn, type_="author", content="Daniel Ulrich Schmitt")
    if hits:
        v_id = hits[0][0]
        print(f'Knoten author "Daniel Ulrich Schmitt" hat id={v_id}')
        _print("ancestors", ancestor(conn, v_id))
    else:
        print('Knoten "Daniel Ulrich Schmitt" nicht gefunden.')

    # ii. Descendant-Knoten von vldb_2023
    print("\n=== ii. descendant ===")
    hits = find_node(conn, s_id="vldb_2023")
    if hits:
        v_id = hits[0][0]
        print(f"Knoten vldb_2023 hat id={v_id}")
        _print("descendants", descendant(conn, v_id))
    else:
        print("Knoten vldb_2023 nicht gefunden.")

    # iii. Following- und preceding-sibling für SchmittKAMM23 und SchalerHS23
    print("\n=== iii. following-sibling / preceding-sibling ===")
    for sid in ("SchmittKAMM23", "SchalerHS23"):
        hits = find_node(conn, s_id=sid)
        if hits:
            v_id = hits[0][0]
            print(f"\n{sid} (id={v_id}):")
            _print(f"following-sibling von {sid}",  following_sibling(conn, v_id))
            _print(f"preceding-sibling von {sid}", preceding_sibling(conn, v_id))
        else:
            print(f"\nKnoten {sid} nicht gefunden.")

    conn.close()
