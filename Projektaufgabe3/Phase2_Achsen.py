"""
Phase 2 – DB-Import und Achse-als-Fenster
"""

import sys
import psycopg2
from pathlib import Path

from Phase2_Transformation_in_EDGE import build_tree
from Phase2_Annotierungsfunktion import annotate_xml

import xml.etree.ElementTree as ET

db_config = {
    "dbname": "toydb",
    "user": "postgres",
    "password": "wortpasst",
    "host": "localhost",
}



# DB-Import

def import_to_db(conn, accel_rows, content_rows, attribute_rows):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM attribute")
        cur.execute("DELETE FROM content")
        cur.execute("DELETE FROM accel")

        cur.executemany(
            "INSERT INTO accel (pre, post, parent, kind, name) VALUES (%s,%s,%s,%s,%s)",
            accel_rows
        )
        cur.executemany(
            "INSERT INTO content (pre, text) VALUES (%s,%s)",
            content_rows
        )
        cur.executemany(
            "INSERT INTO attribute (pre, text) VALUES (%s,%s)",
            attribute_rows
        )
    conn.commit()
    print(f"Import: {len(accel_rows)} accel, {len(content_rows)} content, {len(attribute_rows)} attribute Zeilen.")


# ---------------------------------------------------------------------------
# Hilfsfunktion: Kontextknoten laden
# ---------------------------------------------------------------------------

def get_node_info(conn, v_key):
    with conn.cursor() as cur:
        # Suche per name (z.B. year-Knoten)
        cur.execute("SELECT pre, post, parent FROM accel WHERE name = %s LIMIT 1", (v_key,))
        row = cur.fetchone()
        if row:
            return row

        # Suche per key-Attribut (z.B. SchmittKAMM23)
        cur.execute("""
            SELECT a.pre, a.post, a.parent
            FROM   accel a
            JOIN   attribute att ON a.pre = att.pre
            WHERE  att.text = %s
            LIMIT  1
        """, (f"key={v_key}",))
        row = cur.fetchone()
        if row:
            return row

        # Suche per Textinhalt (z.B. Daniel Ulrich Schmitt)
        cur.execute("""
            SELECT a.pre, a.post, a.parent
            FROM   accel a
            JOIN   content c ON a.pre = c.pre
            WHERE  c.text = %s
            LIMIT  1
        """, (v_key,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Achse-als-Fenster
# ---------------------------------------------------------------------------

def ancestor(conn, v_key):
    v_pre, v_post, v_parent = get_node_info(conn, v_key)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pre, post, parent, kind, name
            FROM   accel
            WHERE  pre  < %s
              AND  post > %s
            ORDER  BY pre
        """, (v_pre, v_post))
        return cur.fetchall()


def descendant(conn, v_key):
    v_pre, v_post, v_parent = get_node_info(conn, v_key)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pre, post, parent, kind, name
            FROM   accel
            WHERE  pre  > %s
              AND  post < %s
            ORDER  BY pre
        """, (v_pre, v_post))
        return cur.fetchall()


def following_sibling(conn, v_key):
    v_pre, v_post, v_parent = get_node_info(conn, v_key)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pre, post, parent, kind, name
            FROM   accel
            WHERE  pre    > %s
              AND  post   > %s
              AND  parent = %s
            ORDER  BY pre
        """, (v_pre, v_post, v_parent))
        return cur.fetchall()


def preceding_sibling(conn, v_key):
    v_pre, v_post, v_parent = get_node_info(conn, v_key)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pre, post, parent, kind, name
            FROM   accel
            WHERE  pre    < %s
              AND  post   < %s
              AND  parent = %s
            ORDER  BY pre
        """, (v_pre, v_post, v_parent))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def _print(label, rows):
    print(f"\n--- {label} ---")
    if not rows:
        print("  (keine Ergebnisse)")
    for row in rows:
        print(" ", row)


# ---------------------------------------------------------------------------
# Korrektheitsprüfung
# ---------------------------------------------------------------------------

def korrektheit(conn):
    # i. ancestor von Daniel Ulrich Schmitt
    print("\n=== i. ancestor ===")
    _print("ancestors von 'Daniel Ulrich Schmitt'", ancestor(conn, "Daniel Ulrich Schmitt"))

    # ii. descendants von vldb_2023
    print("\n=== ii. descendant ===")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.pre, a.post, a.parent
            FROM   accel a
            JOIN   attribute att ON a.pre = att.pre
            WHERE  a.name = 'year' AND att.text = 'value=2023'
              AND  a.parent IN (
                  SELECT a2.pre FROM accel a2
                  JOIN   attribute att2 ON a2.pre = att2.pre
                  WHERE  att2.text = 'name=vldb'
              )
            LIMIT 1
        """)
        row = cur.fetchone()
    if row:
        v_pre, v_post, _ = row
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pre, post, parent, kind, name FROM accel
                WHERE pre > %s AND post < %s ORDER BY pre
            """, (v_pre, v_post))
            _print("descendants von vldb_2023", cur.fetchall())
    else:
        print("  vldb_2023 nicht gefunden")

    # iii. following/preceding-sibling
    print("\n=== iii. following-sibling / preceding-sibling ===")
    for sid in ("SchmittKAMM23", "SchalerHS23"):
        print(f"\n  {sid}:")
        _print(f"following-sibling von {sid}",  following_sibling(conn, sid))
        _print(f"preceding-sibling von {sid}", preceding_sibling(conn, sid))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Phase2_Achsen.py toy_example.txt")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('output_tree')
    build_tree(input_path, output_dir)
    edge_root = ET.parse(output_dir / "edge_model.xml").getroot()

    conn = psycopg2.connect(**db_config)

    # Annotieren
    accel_rows = []
    content_rows = []
    attribute_rows = []
    annotate_xml(edge_root, 1, accel_rows, content_rows, attribute_rows)

    # In DB importieren
    import_to_db(conn, accel_rows, content_rows, attribute_rows)

    # Korrektheit prüfen
    korrektheit(conn)

    conn.close()
