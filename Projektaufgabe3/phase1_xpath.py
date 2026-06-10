"""
XPath-Achsen auf dem EDGE-Modell.

Alle Berechnungen finden als SQL-Rekursion (WITH RECURSIVE) in der Datenbank statt.
Python dient nur als Controller: SQL-Anfrage abschicken, Ergebnis zurückgeben.

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
    """Alle Vorfahren-Knoten von v (ancestor-Achse).

    Idee: Starte beim Elternknoten von v, dann den Elternknoten des Elternknotens,
    usw. – solange bis der Wurzelknoten erreicht ist (kein Elter mehr).
    Das macht WITH RECURSIVE automatisch durch wiederholtes Joinen.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE anc AS (
                -- Basisfall: direkter Elternknoten von v
                -- (finde die Kante die nach v zeigt → deren Startknoten ist der Elter)
                SELECT e."from" AS id
                FROM   edge e
                WHERE  e."to" = %s

                UNION ALL

                -- Rekursiver Schritt: Elternknoten des aktuellen Knotens
                -- (wiederhole so lange, bis kein Elter mehr gefunden wird)
                SELECT e."from"
                FROM   edge e
                JOIN   anc   a ON e."to" = a.id
            )
            -- Knotendetails aus der node-Tabelle holen
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node n
            JOIN   anc  a ON n.id = a.id
            ORDER  BY n.id
        """, (v_id,))
        return cur.fetchall()


def descendant(conn, v_id: int) -> list[tuple]:
    """Alle Nachkommen-Knoten von v (descendant-Achse).

    Idee: Starte bei den direkten Kindern von v, dann deren Kinder,
    usw. – solange bis keine Kinder mehr vorhanden sind (Blattknoten).
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE desc_ AS (
                -- Basisfall: direkte Kinder von v
                -- (finde alle Kanten die von v ausgehen → deren Zielknoten sind die Kinder)
                SELECT e."to" AS id
                FROM   edge e
                WHERE  e."from" = %s

                UNION ALL

                -- Rekursiver Schritt: Kinder der bereits gefundenen Knoten
                SELECT e."to"
                FROM   edge  e
                JOIN   desc_ d ON e."from" = d.id
            )
            -- Knotendetails aus der node-Tabelle holen
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node  n
            JOIN   desc_ d ON n.id = d.id
            ORDER  BY n.id
        """, (v_id,))
        return cur.fetchall()


def following_sibling(conn, v_id: int) -> list[tuple]:
    """Alle nachfolgenden Geschwister-Knoten von v (following-sibling-Achse).

    Geschwister = Knoten mit demselben Elternknoten.
    'Nachfolgend' = kommen im Dokument NACH v → haben eine höhere id,
    weil wir beim Import in Dokumentreihenfolge (DFS) eingefügt haben.
    """
    with conn.cursor() as cur:
        cur.execute("""
            -- Schritt 1: Elternknoten von v finden
            WITH parent AS (
                SELECT e."from" AS parent_id
                FROM   edge e
                WHERE  e."to" = %s
            ),
            -- Schritt 2: alle Kinder des Elternknotens mit id > v_id (= kommen nach v)
            siblings AS (
                SELECT e."to" AS id
                FROM   edge   e
                JOIN   parent p ON e."from" = p.parent_id
                WHERE  e."to" > %s   -- nur Knoten die nach v eingefügt wurden
            )
            SELECT n.id, n.s_id, n.type, n.content
            FROM   node     n
            JOIN   siblings s ON n.id = s.id
            ORDER  BY n.id
        """, (v_id, v_id))
        return cur.fetchall()


def preceding_sibling(conn, v_id: int) -> list[tuple]:
    """Alle vorhergehenden Geschwister-Knoten von v (preceding-sibling-Achse).

    Genau wie following_sibling, nur andersherum:
    id < v_id bedeutet der Knoten wurde VOR v eingefügt → kommt im Dokument vorher.
    """
    with conn.cursor() as cur:
        cur.execute("""
            -- Schritt 1: Elternknoten von v finden
            WITH parent AS (
                SELECT e."from" AS parent_id
                FROM   edge e
                WHERE  e."to" = %s
            ),
            -- Schritt 2: alle Kinder des Elternknotens mit id < v_id (= kommen vor v)
            siblings AS (
                SELECT e."to" AS id
                FROM   edge   e
                JOIN   parent p ON e."from" = p.parent_id
                WHERE  e."to" < %s   -- nur Knoten die vor v eingefügt wurden
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
    """Knoten in der DB suchen – flexibel nach s_id, type oder content filterbar."""
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
    # Ergebniszeilen leserlich formatieren für die Konsolenausgabe
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
# Korrektheitsprüfung (Aufgabe i, ii, iii)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = psycopg2.connect(**db_config)

    # i. Ancestor-Knoten von author "Daniel Ulrich Schmitt"
    # Erwartetes Ergebnis: SchmittKAMM23 → vldb_2023 → vldb → bib (4 Knoten)
    print("=== i. ancestor ===")
    hits = find_node(conn, type_="author", content="Daniel Ulrich Schmitt")
    if hits:
        v_id = hits[0][0]
        print(f'Knoten author "Daniel Ulrich Schmitt" hat id={v_id}')
        _print("ancestors", ancestor(conn, v_id))
    else:
        print('Knoten "Daniel Ulrich Schmitt" nicht gefunden.')

    # ii. Descendant-Knoten von vldb_2023
    # Erwartetes Ergebnis: SchmittKAMM23 + alle seine Felder + SchalerHS23 + alle ihre Felder (28 Knoten)
    print("\n=== ii. descendant ===")
    hits = find_node(conn, s_id="vldb_2023")
    if hits:
        v_id = hits[0][0]
        print(f"Knoten vldb_2023 hat id={v_id}")
        _print("descendants", descendant(conn, v_id))
    else:
        print("Knoten vldb_2023 nicht gefunden.")

    # iii. Following- und preceding-sibling für SchmittKAMM23 und SchalerHS23
    # Beide liegen unter vldb_2023 → sind Geschwister
    # SchmittKAMM23 kommt zuerst → hat einen following-sibling (SchalerHS23), keinen preceding
    # SchalerHS23 kommt danach → hat einen preceding-sibling (SchmittKAMM23), keinen following
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
