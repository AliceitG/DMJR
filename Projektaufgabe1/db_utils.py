import os

import psycopg2
from psycopg2 import sql

from common import AttributeSpec, classify_type, dataset_object_names


def connect_db():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        database=os.getenv("PGDATABASE", "projektaufgabe1"),
        user=os.getenv("PGUSER", "projektaufgabe1_user"),
        password=os.getenv("PGPASSWORD", "1234"),
    )


def fetch_attribute_specs(cur, table_name):
    cur.execute(
        """
        SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod) AS sql_type
        FROM pg_attribute AS a
        JOIN pg_class AS c ON c.oid = a.attrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE c.relname = %s
          AND n.nspname = current_schema()
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum;
        """,
        (table_name,),
    )
    rows = cur.fetchall()
    if not rows:
        raise ValueError(f"Table '{table_name}' was not found in the current schema.")

    specs = []
    for column_name, sql_type in rows:
        if column_name == "oid":
            continue
        specs.append(AttributeSpec(column_name, sql_type, classify_type(sql_type)))
    return specs


def drop_relation(cur, relation_name, relation_kind):
    statement = sql.SQL("DROP {} IF EXISTS {} CASCADE;").format(
        sql.SQL(relation_kind),
        sql.Identifier(relation_name),
    )
    cur.execute(statement)


def drop_dataset_objects(cur, table_name):
    names = dataset_object_names(table_name)
    for view_name in [
        names["generator_audit"],
        names["value_frequency"],
        names["null_stats"],
        names["view"],
        names["v_all"],
    ]:
        drop_relation(cur, view_name, "VIEW")

    for table in [names["oids"], names["v_str"], names["v_int"], table_name]:
        drop_relation(cur, table, "TABLE")


def drop_api_functions(cur):
    cur.execute("DROP FUNCTION IF EXISTS q_i(integer) CASCADE;")
    cur.execute("DROP FUNCTION IF EXISTS q_ii(text, text) CASCADE;")
    cur.execute("DROP FUNCTION IF EXISTS q_ii(text, integer) CASCADE;")


def relation_exists(cur, relation_name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (relation_name,))
    return bool(cur.fetchone()[0])


def print_relation(relation_name, limit=20):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {} ORDER BY 1 LIMIT %s;").format(sql.Identifier(relation_name)),
                (limit,),
            )
            rows = cur.fetchall()

    print(f"\n--- {relation_name} (limit {limit}) ---")
    for row in rows:
        print(row)


def compare_relations(left_relation, right_relation, label=None):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    SELECT * FROM {}
                    EXCEPT ALL
                    SELECT * FROM {};
                    """
                ).format(sql.Identifier(left_relation), sql.Identifier(right_relation))
            )
            left_minus_right = cur.fetchall()

            cur.execute(
                sql.SQL(
                    """
                    SELECT * FROM {}
                    EXCEPT ALL
                    SELECT * FROM {};
                    """
                ).format(sql.Identifier(right_relation), sql.Identifier(left_relation))
            )
            right_minus_left = cur.fetchall()

    is_equal = not left_minus_right and not right_minus_left

    if label:
        print(f"\n=== {label} ===")
        print(f"{left_relation} MINUS {right_relation}: {left_minus_right}")
        print(f"{right_relation} MINUS {left_relation}: {right_minus_left}")
        print(f"Result: {'OK' if is_equal else 'DIFF'}")

    return is_equal, left_minus_right, right_minus_left
