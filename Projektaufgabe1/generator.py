import random

from psycopg2 import extras, sql

from common import (
    DEFAULT_VALUE_FREQUENCY,
    MAX_ATTRIBUTES,
    dataset_object_names,
    quoted_identifier,
    quoted_literal,
)
from db_utils import connect_db, drop_dataset_objects, fetch_attribute_specs


def create_generator_audit_views(
    cur,
    conn,
    table_name,
    requested_num_tuples,
    requested_sparsity,
    requested_num_attributes,
):
    names = dataset_object_names(table_name)
    specs = fetch_attribute_specs(cur, table_name)
    q_table = quoted_identifier(conn, table_name)
    q_null_stats = quoted_identifier(conn, names["null_stats"])
    q_value_frequency = quoted_identifier(conn, names["value_frequency"])
    q_generator_audit = quoted_identifier(conn, names["generator_audit"])

    null_parts = []
    frequency_parts = []

    for spec in specs:
        q_attr = quoted_identifier(conn, spec.name)
        attr_literal = quoted_literal(conn, spec.name)

        null_parts.append(
            "SELECT "
            f"{attr_literal} AS attribute, "
            f"COUNT(*) FILTER (WHERE {q_attr} IS NULL) AS null_count, "
            f"ROUND(AVG(CASE WHEN {q_attr} IS NULL THEN 1.0 ELSE 0.0 END)::numeric, 4) AS null_ratio "
            f"FROM {q_table}"
        )

        frequency_parts.append(
            "SELECT "
            f"{attr_literal} AS attribute, "
            f"{q_attr}::text AS value, "
            "COUNT(*) AS frequency "
            f"FROM {q_table} "
            f"WHERE {q_attr} IS NOT NULL "
            f"GROUP BY {q_attr}"
        )

    cur.execute(f"CREATE VIEW {q_null_stats} AS " + " UNION ALL ".join(null_parts) + " ORDER BY attribute;")
    cur.execute(
        f"CREATE VIEW {q_value_frequency} AS "
        + " UNION ALL ".join(frequency_parts)
        + " ORDER BY attribute, value;"
    )

    cur.execute(
        f"""
        CREATE VIEW {q_generator_audit} AS
        SELECT
            {quoted_literal(conn, requested_num_tuples)}::integer AS requested_num_tuples,
            {quoted_literal(conn, requested_sparsity)}::numeric AS requested_sparsity,
            {quoted_literal(conn, requested_num_attributes)}::integer AS requested_num_attributes,
            (SELECT COUNT(*) FROM {q_table}) AS actual_num_tuples,
            (SELECT ROUND(AVG(null_ratio), 4) FROM {q_null_stats}) AS avg_null_ratio,
            (SELECT COALESCE(MAX(frequency), 0) FROM {q_value_frequency}) AS max_value_frequency;
        """
    )


def generate(
    table_name="h_generated",
    num_tuples=2000,
    sparsity=0.75,
    num_attributes=6,
    value_frequency=DEFAULT_VALUE_FREQUENCY,
    seed=42,
):
    if num_tuples <= 0:
        raise ValueError("num_tuples must be > 0.")
    if not 0 <= sparsity <= 1:
        raise ValueError("sparsity must be in [0, 1].")
    if num_attributes <= 0:
        raise ValueError("num_attributes must be > 0.")
    if num_attributes > MAX_ATTRIBUTES:
        raise ValueError(f"num_attributes must be <= {MAX_ATTRIBUTES}.")
    if value_frequency <= 0:
        raise ValueError("value_frequency must be > 0.")

    rng = random.Random(seed)
    names = dataset_object_names(table_name)

    with connect_db() as conn:
        with conn.cursor() as cur:
            drop_dataset_objects(cur, table_name)

            column_defs = [sql.SQL("oid INTEGER PRIMARY KEY")]
            column_names = ["oid"]
            for index in range(1, num_attributes + 1):
                attr_name = f"a{index}"
                sql_type = "TEXT" if index % 2 == 1 else "INTEGER"
                column_defs.append(
                    sql.SQL("{} {}").format(sql.Identifier(attr_name), sql.SQL(sql_type))
                )
                column_names.append(attr_name)

            cur.execute(
                sql.SQL("CREATE TABLE {} ({});").format(
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(column_defs),
                )
            )

            insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
            ).as_string(conn)

            buffer = []
            for oid in range(1, num_tuples + 1):
                row = [oid]
                group_id = (oid - 1) // value_frequency

                for index in range(1, num_attributes + 1):
                    if rng.random() < sparsity:
                        row.append(None)
                    elif index % 2 == 1:
                        row.append(f"a{index}_v{group_id}")
                    else:
                        row.append(group_id)

                buffer.append(tuple(row))
                if len(buffer) == 1000:
                    extras.execute_values(cur, insert_sql, buffer, page_size=1000)
                    buffer.clear()

            if buffer:
                extras.execute_values(cur, insert_sql, buffer, page_size=1000)

            create_generator_audit_views(cur, conn, table_name, num_tuples, sparsity, num_attributes)

    print(
        f"Generated table '{table_name}' with {num_tuples} tuples, "
        f"sparsity {sparsity:.4f}, {num_attributes} attributes."
    )
    print(
        f"Audit views: {names['null_stats']}, {names['value_frequency']}, {names['generator_audit']}."
    )
