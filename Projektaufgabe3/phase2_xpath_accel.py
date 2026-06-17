"""
XPath-Achsen als Fenster-Anfragen auf dem Accelerator-Schema (Phase 2).

Statt rekursiver SQL-Anfragen (Phase 1) nutzen wir hier die pre-/post-Ordnung
der Relation accel, um jede Achse als einfache Bereichsabfrage auszudrücken:

  ancestor(v)          : pre(n) < pre(v)  AND  post(n) > post(v)
  descendant(v)        : pre(n) > pre(v)  AND  post(n) < post(v)
  following-sibling(v) : parent(n) = parent(v)  AND  pre(n) > pre(v)
  preceding-sibling(v) : parent(n) = parent(v)  AND  pre(n) < pre(v)

Verwendung:
    python phase2_xpath_accel.py

Voraussetzungen:
    1. Phase2-Schemaerstellung.sql in DB eingespielt
    2. Phase2-Annotierungsfunktion.py toy_example.txt  ausgeführt
"""

import psycopg2

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}


# ---------------------------------------------------------------------------
# Knoten-Lookup
# ---------------------------------------------------------------------------

def find_by_attr(cur, attr_value: str):
    """Gibt (pre, post, parent, kind, name) für den Knoten zurück, dessen
    attribute-Eintrag exakt attr_value lautet, z.B. 'key=SchmittKAMM23'."""
    cur.execute("""
        SELECT a.pre, a.post, a.parent, a.kind, a.name
        FROM   accel     a
        JOIN   attribute t ON t.pre = a.pre
        WHERE  t.text = %s
        LIMIT 1
    """, (attr_value,))
    return cur.fetchone()


def find_by_content(cur, text: str):
    """Gibt (pre, post, parent, kind, name) für den Knoten zurück, dessen
    content-Eintrag den gesuchten Text enthält."""
    cur.execute("""
        SELECT a.pre, a.post, a.parent, a.kind, a.name
        FROM   accel   a
        JOIN   content c ON c.pre = a.pre
        WHERE  c.text = %s
        LIMIT 1
    """, (text,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# XPath-Achsen als Fenster-Anfragen
# ---------------------------------------------------------------------------

def ancestor(cur, pre_v: int, post_v: int) -> list[tuple]:
    """Alle Vorfahren von v: pre(n) < pre(v) AND post(n) > post(v)."""
    cur.execute("""
        SELECT pre, post, parent, kind, name
        FROM   accel
        WHERE  pre < %s AND post > %s
        ORDER  BY pre
    """, (pre_v, post_v))
    return cur.fetchall()


def descendant(cur, pre_v: int, post_v: int) -> list[tuple]:
    """Alle Nachkommen von v: pre(n) > pre(v) AND post(n) < post(v)."""
    cur.execute("""
        SELECT pre, post, parent, kind, name
        FROM   accel
        WHERE  pre > %s AND post < %s
        ORDER  BY pre
    """, (pre_v, post_v))
    return cur.fetchall()


def following_sibling(cur, pre_v: int, parent_v) -> list[tuple]:
    """Nachfolgende Geschwister: gleicher parent, pre(n) > pre(v)."""
    cur.execute("""
        SELECT pre, post, parent, kind, name
        FROM   accel
        WHERE  parent = %s AND pre > %s
        ORDER  BY pre
    """, (parent_v, pre_v))
    return cur.fetchall()


def preceding_sibling(cur, pre_v: int, parent_v) -> list[tuple]:
    """Vorhergehende Geschwister: gleicher parent, pre(n) < pre(v)."""
    cur.execute("""
        SELECT pre, post, parent, kind, name
        FROM   accel
        WHERE  parent = %s AND pre < %s
        ORDER  BY pre
    """, (parent_v, pre_v))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Ausgabe-Hilfe
# ---------------------------------------------------------------------------

def _fmt(rows: list[tuple]) -> str:
    if not rows:
        return "  (keine Ergebnisse)"
    lines = []
    for pre, post, parent, kind, name in rows:
        lines.append(f"  pre={pre}, post={post}, parent={parent}, {kind} <{name}>")
    return "\n".join(lines)


def _print(label: str, rows: list[tuple]) -> None:
    print(f"\n--- {label} (Größe={len(rows)}) ---")
    print(_fmt(rows))


# ---------------------------------------------------------------------------
# Korrektheitsprüfung am Toy-Beispiel
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = psycopg2.connect(**db_config)

    with conn.cursor() as cur:

        # i. ancestor – Vorfahren von author "Daniel Ulrich Schmitt"
        print("=== i. ancestor ===")
        node = find_by_content(cur, "Daniel Ulrich Schmitt")
        if node:
            pre_v, post_v, parent_v, kind, name = node
            print(f'Knoten <{name}> "Daniel Ulrich Schmitt": pre={pre_v}, post={post_v}')
            _print("ancestors", ancestor(cur, pre_v, post_v))
        else:
            print("Knoten nicht gefunden – accel-Tabelle befüllt?")

        # ii. descendant – Nachkommen des year-Knotens "2023" unter vldb
        #     (erkennbar an attribute value=2023 unter einem venue-Knoten)
        print("\n=== ii. descendant ===")
        node = find_by_attr(cur, "value=2023")
        if node:
            pre_v, post_v, parent_v, kind, name = node
            print(f'Knoten <{name}> value=2023: pre={pre_v}, post={post_v}')
            _print("descendants", descendant(cur, pre_v, post_v))
        else:
            print("year-Knoten (value=2023) nicht gefunden.")

        # iii. following-/preceding-sibling für SchmittKAMM23 und SchalerHS23
        print("\n=== iii. following-sibling / preceding-sibling ===")
        for pub_key in ("SchmittKAMM23", "SchalerHS23"):
            node = find_by_attr(cur, f"key={pub_key}")
            if node:
                pre_v, post_v, parent_v, kind, name = node
                print(f"\n{pub_key} (<{name}>): pre={pre_v}, post={post_v}, parent={parent_v}")
                _print(f"following-sibling von {pub_key}",
                       following_sibling(cur, pre_v, parent_v))
                _print(f"preceding-sibling von {pub_key}",
                       preceding_sibling(cur, pre_v, parent_v))
            else:
                print(f"\n{pub_key} nicht gefunden.")

    conn.close()
