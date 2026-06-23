import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import psycopg2

from Projektaufgabe3.phase2.Phase2_Transformation_in_EDGE import build_tree

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}

def schema1d(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS accel1d")
        cur.execute("""
            CREATE TABLE accel1d (
                pre    INTEGER,
                post   INTEGER,
                parent INTEGER,
                kind   TEXT,
                name   TEXT
            )
        """)
        cur.execute("CREATE INDEX accel1d_pre_idx ON accel1d (pre)")
        conn.commit()
        print("Schema accel1d angelegt.")

def annotate_xml(elem, counter=1, rows_accel=None, rows_content=None, rows_attribute=None, parent_pre=None):
    """
    Nargiz code Kopiert. es verwendet genau einen counter und daher eine Dimension.
    """
    if rows_accel is None:
        rows_accel = []
    if rows_content is None:
        rows_content = []
    if rows_attribute is None:
        rows_attribute = []

    my_pre = counter
    counter += 1

    name = elem.tag
    kind = 'element'
    row_index = len(rows_accel)
    rows_accel.append((my_pre, None, parent_pre, kind, name))

    text = (elem.text or '').strip()
    if text:
        rows_content.append((my_pre, text))

    for attr_name, attr_value in elem.attrib.items():
        rows_attribute.append((my_pre, f"{attr_name}={attr_value}"))

    for child in list(elem):
        counter = annotate_xml(child, counter, rows_accel, rows_content, rows_attribute, my_pre)

    my_post = counter
    counter += 1
    rows_accel[row_index] = (my_pre, my_post, parent_pre, kind, name)

    return counter

def import_to_db(conn, accel_rows, content_rows, attribute_rows):
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO accel1d (pre, post, parent, kind, name) VALUES (%s,%s,%s,%s,%s)",
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
    print(f"Import: {len(accel_rows)} accel1d Zeilen.")

# Help funktion copy
def get_node_info(conn, v_key):
    with conn.cursor() as cur:
        # Suche per name (z.B. year-Knoten)
        cur.execute("SELECT pre, post, parent FROM accel1d WHERE name = %s LIMIT 1", (v_key,))
        row = cur.fetchone()
        if row:
            return row

        # Suche per key-Attribut (z.B. SchmittKAMM23)
        cur.execute("""
                    SELECT a.pre, a.post, a.parent
                    FROM accel1d a
                             JOIN attribute att ON a.pre = att.pre
                    WHERE att.text = %s LIMIT  1
                    """, (f"key={v_key}",))
        row = cur.fetchone()
        if row:
            return row

        # Suche per Textinhalt (z.B. Daniel Ulrich Schmitt)
        cur.execute("""
                    SELECT a.pre, a.post, a.parent
                    FROM accel1d a
                             JOIN content c ON a.pre = c.pre
                    WHERE c.text = %s LIMIT  1
                    """, (v_key,))
        return cur.fetchone()


def descendant1d(conn, v_key):
    """pre(v) < pre(n) < post(v) """
    v_pre, v_post, v_parent = get_node_info(conn, v_key)
    with conn.cursor() as cur:
        cur.execute("""
                    SELECT pre, post, parent, kind, name
                    FROM accel1d
                    WHERE pre > %s
                      AND pre < %s
                    ORDER BY pre
                    """, (v_pre, v_post))
        return cur.fetchall()


def _print(label, rows):
    print(f"\n--- {label} ---")
    if not rows:
        print("  (keine Ergebnisse)")
    for row in rows:
        print(" ", row)


def korrektheit(conn):
    # descendants von vldb_2023 (gleicher Ausschnitt wie Phase 2, Punkt ii.)
    print("\n=== descendant (1D-Achse) – vldb_2023 ===")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.pre, a.post, a.parent
            FROM   accel1d a
            JOIN   attribute att ON a.pre = att.pre
            WHERE  a.name = 'year' AND att.text = 'value=2023'
              AND  a.parent IN (
                  SELECT a2.pre FROM accel1d a2
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
                SELECT pre, post, parent, kind, name
                FROM   accel1d
                WHERE  pre > %s AND pre < %s
                ORDER  BY pre
            """, (v_pre, v_post))
            _print("descendants von vldb_2023 [1D]", cur.fetchall())
    else:
        print("  vldb_2023 nicht gefunden")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Phase3_SingleAxis.py toy_example.txt")
        sys.exit(1)

    #Copy paste aus Achsen.py
    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('output_tree')
    build_tree(input_path, output_dir)
    edge_root = ET.parse(output_dir / "edge_model.xml").getroot()

    conn = psycopg2.connect(**db_config)

    # Annotieren (gleiche Funktion wie Phase 2)
    accel_rows = []
    content_rows = []
    attribute_rows = []
    annotate_xml(edge_root, 1, accel_rows, content_rows, attribute_rows)

    # 1D Schema
    schema1d(conn)

    # In accel1d importieren
    import_to_db(conn, accel_rows, content_rows, attribute_rows)

    # Korrektheit prüfen
    korrektheit(conn)

    conn.close()
