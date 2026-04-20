from psycopg2 import sql

from common import dataset_object_names, make_object_name, quoted_identifier, quoted_literal
from db_utils import compare_relations, connect_db, drop_relation, fetch_attribute_specs, relation_exists


def h2v_general(horizontal_table):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)

            for view_name in [names["view"], names["v_all"]]:
                drop_relation(cur, view_name, "VIEW")
            for table_name in [names["oids"], names["v_str"], names["v_int"]]:
                drop_relation(cur, table_name, "TABLE")

            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE {} (
                        oid INTEGER NOT NULL
                    );
                    """
                ).format(sql.Identifier(names["oids"]))
            )
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE {} (
                        oid INTEGER NOT NULL,
                        "key" TEXT NOT NULL,
                        val TEXT NOT NULL
                    );
                    """
                ).format(sql.Identifier(names["v_str"]))
            )
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE {} (
                        oid INTEGER NOT NULL,
                        "key" TEXT NOT NULL,
                        val INTEGER NOT NULL
                    );
                    """
                ).format(sql.Identifier(names["v_int"]))
            )

            cur.execute(
                sql.SQL("INSERT INTO {} (oid) SELECT oid FROM {} ORDER BY oid;").format(
                    sql.Identifier(names["oids"]),
                    sql.Identifier(horizontal_table),
                )
            )

            for spec in specs:
                target_table = names["v_str"] if spec.fragment_kind == "str" else names["v_int"]
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} (oid, "key", val)
                        SELECT oid, %s, {}
                        FROM {}
                        WHERE {} IS NOT NULL
                        ORDER BY oid;
                        """
                    ).format(
                        sql.Identifier(target_table),
                        sql.Identifier(spec.name),
                        sql.Identifier(horizontal_table),
                        sql.Identifier(spec.name),
                    ),
                    (spec.name,),
                )

            cur.execute(
                sql.SQL(
                    """
                    CREATE VIEW {} AS
                    SELECT oid, "key", val::text AS val
                    FROM {}
                    UNION ALL
                    SELECT oid, "key", val::text AS val
                    FROM {};
                    """
                ).format(
                    sql.Identifier(names["v_all"]),
                    sql.Identifier(names["v_str"]),
                    sql.Identifier(names["v_int"]),
                )
            )

    print(
        f"H2V completed for '{horizontal_table}'. "
        f"Created {names['oids']}, {names['v_str']}, {names['v_int']}, {names['v_all']}."
    )


def create_v2h_view(horizontal_table):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)
            drop_relation(cur, names["view"], "VIEW")

            q_view = quoted_identifier(conn, names["view"])
            q_oids = quoted_identifier(conn, names["oids"])
            q_v_str = quoted_identifier(conn, names["v_str"])
            q_v_int = quoted_identifier(conn, names["v_int"])

            select_parts = ["o.oid"]
            join_parts = []

            for index, spec in enumerate(specs, start=1):
                alias = f"j{index}"
                q_alias_column = quoted_identifier(conn, spec.name)
                q_key_literal = quoted_literal(conn, spec.name)
                source = q_v_str if spec.fragment_kind == "str" else q_v_int

                select_parts.append(f'{alias}.val AS {q_alias_column}')
                join_parts.append(
                    f"LEFT JOIN {source} AS {alias} "
                    f'ON o.oid = {alias}.oid AND {alias}."key" = {q_key_literal}'
                )

            cur.execute(
                f"""
                CREATE VIEW {q_view} AS
                SELECT
                    {", ".join(select_parts)}
                FROM {q_oids} AS o
                {' '.join(join_parts)}
                ORDER BY o.oid;
                """
            )

    print(f"V2H view created: {names['view']}.")


def ensure_vertical_layout(horizontal_table, require_view=False):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            has_oids = relation_exists(cur, names["oids"])
            has_v_str = relation_exists(cur, names["v_str"])
            has_v_int = relation_exists(cur, names["v_int"])
            has_view = relation_exists(cur, names["view"])

    if not (has_oids and has_v_str and has_v_int):
        h2v_general(horizontal_table)
        has_view = False

    if require_view and not has_view:
        create_v2h_view(horizontal_table)


def test_general_operator_correctness(horizontal_table, reference_vertical_view=None):
    names = dataset_object_names(horizontal_table)
    checks_ok = True

    if reference_vertical_view is not None:
        vertical_ok, _, _ = compare_relations(
            reference_vertical_view,
            names["v_all"],
            f"H2V correctness for '{horizontal_table}'",
        )
        checks_ok = checks_ok and vertical_ok

    horizontal_ok, _, _ = compare_relations(
        horizontal_table,
        names["view"],
        f"V2H correctness for '{horizontal_table}'",
    )
    return checks_ok and horizontal_ok


def create_horizontal_indexes(horizontal_table):
    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)
            for spec in specs:
                index_name = make_object_name(horizontal_table, spec.name, "idx")
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({});").format(
                        sql.Identifier(index_name),
                        sql.Identifier(horizontal_table),
                        sql.Identifier(spec.name),
                    )
                )

    print(f"Horizontal indexes created for '{horizontal_table}'.")


def drop_horizontal_indexes(horizontal_table):
    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)
            for spec in specs:
                index_name = make_object_name(horizontal_table, spec.name, "idx")
                cur.execute(sql.SQL("DROP INDEX IF EXISTS {};").format(sql.Identifier(index_name)))


def drop_vertical_indexes(horizontal_table):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = ANY(%s);
                """,
                ([names["oids"], names["v_str"], names["v_int"]],),
            )
            index_names = [row[0] for row in cur.fetchall()]
            for index_name in index_names:
                cur.execute(sql.SQL("DROP INDEX IF EXISTS {};").format(sql.Identifier(index_name)))


def create_vertical_indexes(horizontal_table, mode="basic"):
    if mode not in {"basic", "covering", "partial"}:
        raise ValueError("mode must be one of: basic, covering, partial.")

    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)

            oid_index = make_object_name(horizontal_table, "oids", "oid_idx")
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (oid);").format(
                    sql.Identifier(oid_index),
                    sql.Identifier(names["oids"]),
                )
            )

            if mode == "basic":
                base_index_defs = [
                    (make_object_name(horizontal_table, "v_str", "oid_key_idx"), names["v_str"], '(oid, "key")'),
                    (make_object_name(horizontal_table, "v_int", "oid_key_idx"), names["v_int"], '(oid, "key")'),
                    (make_object_name(horizontal_table, "v_str", "key_val_idx"), names["v_str"], '("key", val)'),
                    (make_object_name(horizontal_table, "v_int", "key_val_idx"), names["v_int"], '("key", val)'),
                ]
            else:
                base_index_defs = [
                    (make_object_name(horizontal_table, "v_str", "oid_key_val_idx"), names["v_str"], '(oid, "key", val)'),
                    (make_object_name(horizontal_table, "v_int", "oid_key_val_idx"), names["v_int"], '(oid, "key", val)'),
                    (make_object_name(horizontal_table, "v_str", "key_val_oid_idx"), names["v_str"], '("key", val, oid)'),
                    (make_object_name(horizontal_table, "v_int", "key_val_oid_idx"), names["v_int"], '("key", val, oid)'),
                ]

            for index_name, table_name, index_def in base_index_defs:
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS {quoted_identifier(conn, index_name)} "
                    f"ON {quoted_identifier(conn, table_name)} {index_def};"
                )

            if mode == "partial":
                for spec in specs:
                    fragment = names["v_str"] if spec.fragment_kind == "str" else names["v_int"]
                    index_name = make_object_name(horizontal_table, spec.name, "partial_idx")
                    cur.execute(
                        f"CREATE INDEX IF NOT EXISTS {quoted_identifier(conn, index_name)} "
                        f"ON {quoted_identifier(conn, fragment)} (val, oid) "
                        f'WHERE "key" = {quoted_literal(conn, spec.name)};'
                    )

    print(f"Vertical indexes created for '{horizontal_table}' with mode '{mode}'.")


def analyze_dataset(horizontal_table):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            for relation_name in [horizontal_table, names["oids"], names["v_str"], names["v_int"]]:
                cur.execute(sql.SQL("ANALYZE {};").format(sql.Identifier(relation_name)))


def relation_total_size_bytes(cur, relation_name):
    cur.execute(
        "SELECT COALESCE(pg_total_relation_size(to_regclass(%s)), 0);",
        (relation_name,),
    )
    return int(cur.fetchone()[0])


def measure_storage(horizontal_table):
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            horizontal_bytes = relation_total_size_bytes(cur, horizontal_table)
            oid_bytes = relation_total_size_bytes(cur, names["oids"])
            str_bytes = relation_total_size_bytes(cur, names["v_str"])
            int_bytes = relation_total_size_bytes(cur, names["v_int"])

    vertical_bytes = oid_bytes + str_bytes + int_bytes
    return {
        "horizontal_bytes": horizontal_bytes,
        "horizontal_mb": round(horizontal_bytes / (1024 * 1024), 4),
        "vertical_bytes": vertical_bytes,
        "vertical_mb": round(vertical_bytes / (1024 * 1024), 4),
        "vertical_oid_bytes": oid_bytes,
        "vertical_str_bytes": str_bytes,
        "vertical_int_bytes": int_bytes,
    }


def fetch_distinct_non_null_values(cur, table_name, attribute_name):
    cur.execute(
        sql.SQL(
            """
            SELECT DISTINCT {}
            FROM {}
            WHERE {} IS NOT NULL;
            """
        ).format(
            sql.Identifier(attribute_name),
            sql.Identifier(table_name),
            sql.Identifier(attribute_name),
        )
    )
    return [row[0] for row in cur.fetchall()]


def prepare_query_ii_samples(cur, table_name):
    specs = fetch_attribute_specs(cur, table_name)
    domains = {}
    eligible_specs = []

    for spec in specs:
        domain = fetch_distinct_non_null_values(cur, table_name, spec.name)
        domains[spec.name] = domain
        if domain:
            eligible_specs.append(spec)

    if not eligible_specs:
        raise RuntimeError("Query type ii cannot be benchmarked because every attribute domain is empty.")

    return eligible_specs, domains
