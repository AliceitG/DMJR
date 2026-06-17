from pathlib import Path
import sys
import psycopg2
from Phase2_Transformation_in_EDGE import build_tree

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost",
}


def annotate_xml(elem, counter=1, rows_accel=None, rows_content=None, rows_attribute=None, parent_pre=None):
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


def insert_to_db(rows_accel, rows_content, rows_attribute):
    conn = psycopg2.connect(**db_config)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO accel (pre, post, parent, kind, name) VALUES (%s,%s,%s,%s,%s)",
                    rows_accel,
                )
                cur.executemany(
                    "INSERT INTO content (pre, text) VALUES (%s,%s)",
                    rows_content,
                )
                cur.executemany(
                    "INSERT INTO attribute (pre, text) VALUES (%s,%s)",
                    rows_attribute,
                )
        print("DB-Import von accel/content/attribute erfolgreich.")
    finally:
        conn.close()


# Test für ganzes Toy-Beispiel und einen Teilabschnitt:
if __name__ == "__main__":
    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('output_tree')
    edge_root = build_tree(input_path, output_dir)

    if edge_root is None:
        print("FEHLER: build_tree hat None zurückgegeben.")
        sys.exit(1)

    accel_rows = []
    content_rows = []
    attribute_rows = []

    annotate_xml(edge_root, 1, accel_rows, content_rows, attribute_rows)

    print('ACCEL')
    for row in accel_rows:
        print(row)

    print('\nCONTENT')
    for row in content_rows:
        print(row)

    print('\nATTRIBUTE')
    for row in attribute_rows:
        print(row)

    # In Datenbank importieren
    try:
        insert_to_db(accel_rows, content_rows, attribute_rows)
    except Exception as e:
        print(f"DB-Import fehlgeschlagen (tabellen vorhanden?): {e}")

    target_key = 'SchmittKAMM23'
    target_article = None

    for pre, post, parent, kind, name in accel_rows:
        if kind == 'element' and name == 'article':
            for attr_pre, attr_text in attribute_rows:
                if attr_pre == pre and attr_text == f'key={target_key}':
                    target_article = (pre, post, parent, kind, name)
                    break
        if target_article is not None:
            break

    if target_article is not None:
        article_pre, article_post, article_parent, _, _ = target_article

        ancestors = {}
        for pre, post, parent, kind, name in accel_rows:
            ancestors[pre] = (post, parent, kind, name)

        path_pres = []
        current = article_pre
        while current is not None:
            path_pres.append(current)
            current = ancestors[current][1]
        path_pres.reverse()

        print('\nKORREKTHEITSNACHWEIS: SCHMITTKAMM23')
        print('PFAD ZUR WURZEL')
        for pre in path_pres:
            post, parent, kind, name = ancestors[pre]
            print((pre, post, parent, kind, name))

        print('\nTEILBAUM ACCEL')
        for row in accel_rows:
            pre, post, parent, kind, name = row
            if article_pre <= pre <= article_post:
                print(row)

        print('\nTEILBAUM CONTENT')
        for row in content_rows:
            pre, text = row
            if article_pre <= pre <= article_post:
                print(row)

        print('\nTEILBAUM ATTRIBUTE')
        for row in attribute_rows:
            pre, text = row
            if pre in path_pres or (article_pre <= pre <= article_post):
                print(row)
    else:
        print(f'\nKein article mit key={target_key} gefunden.')
