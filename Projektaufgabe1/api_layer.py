import json

from psycopg2 import sql

from common import dataset_object_names, ensure_results_dir, quoted_identifier, quoted_literal, RESULTS_DIR
from db_utils import connect_db, drop_api_functions, fetch_attribute_specs
from operators import analyze_dataset, ensure_vertical_layout, fetch_distinct_non_null_values


def create_api_functions(horizontal_table):
    ensure_vertical_layout(horizontal_table, require_view=False)
    names = dataset_object_names(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            specs = fetch_attribute_specs(cur, horizontal_table)
            drop_api_functions(cur)

            q_oids = quoted_identifier(conn, names["oids"])
            q_v_str = quoted_identifier(conn, names["v_str"])
            q_v_int = quoted_identifier(conn, names["v_int"])

            return_columns = ['"oid" integer']
            select_parts = ["o.oid"]

            for spec in specs:
                q_column = quoted_identifier(conn, spec.name)
                q_key_literal = quoted_literal(conn, spec.name)
                q_fragment = q_v_str if spec.fragment_kind == "str" else q_v_int

                return_columns.append(f"{q_column} {spec.sql_type}")
                select_parts.append(
                    f"(SELECT val FROM {q_fragment} "
                    f'WHERE oid = o.oid AND "key" = {q_key_literal} LIMIT 1) AS {q_column}'
                )

            cur.execute(
                f"""
                CREATE FUNCTION q_i(p_oid integer)
                RETURNS TABLE ({", ".join(return_columns)})
                LANGUAGE SQL
                STABLE
                AS $$
                    SELECT
                        {", ".join(select_parts)}
                    FROM {q_oids} AS o
                    WHERE o.oid = p_oid
                $$;
                """
            )

            cur.execute(
                f"""
                CREATE FUNCTION q_ii(p_key text, p_val text)
                RETURNS TABLE (oid integer)
                LANGUAGE SQL
                STABLE
                AS $$
                    SELECT oid
                    FROM {q_v_str}
                    WHERE "key" = p_key
                      AND val = p_val
                    ORDER BY oid
                $$;
                """
            )

            cur.execute(
                f"""
                CREATE FUNCTION q_ii(p_key text, p_val integer)
                RETURNS TABLE (oid integer)
                LANGUAGE SQL
                STABLE
                AS $$
                    SELECT oid
                    FROM {q_v_int}
                    WHERE "key" = p_key
                      AND val = p_val
                    ORDER BY oid
                $$;
                """
            )

    print("DB API functions created: q_i(integer), q_ii(text, text), q_ii(text, integer).")


def fetch_query_ii_sample(cur, table_name, attribute_name=None):
    specs = fetch_attribute_specs(cur, table_name)
    spec_map = {spec.name: spec for spec in specs}

    if attribute_name is not None:
        if attribute_name not in spec_map:
            raise ValueError(f"Unknown attribute '{attribute_name}'.")
        spec = spec_map[attribute_name]
        domain = fetch_distinct_non_null_values(cur, table_name, spec.name)
        if not domain:
            raise RuntimeError(f"Attribute '{attribute_name}' only contains NULL.")
        return spec, domain[0]

    for spec in specs:
        domain = fetch_distinct_non_null_values(cur, table_name, spec.name)
        if domain:
            return spec, domain[0]

    raise RuntimeError("No attribute with a non-null domain was found.")


def explain_text(cur, statement, params):
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {statement}", params)
    return "\n".join(row[0] for row in cur.fetchall())


def compare_explain_plans(horizontal_table, sample_oid=1, sample_attribute=None):
    names = dataset_object_names(horizontal_table)
    ensure_vertical_layout(horizontal_table, require_view=True)
    create_api_functions(horizontal_table)
    analyze_dataset(horizontal_table)

    with connect_db() as conn:
        with conn.cursor() as cur:
            spec, value = fetch_query_ii_sample(cur, horizontal_table, sample_attribute)

            view_q_i = sql.SQL("SELECT * FROM {} WHERE oid = %s").format(
                sql.Identifier(names["view"])
            ).as_string(conn)
            api_q_i = "SELECT * FROM q_i(%s)"

            view_q_ii = sql.SQL("SELECT oid FROM {} WHERE {} = %s").format(
                sql.Identifier(names["view"]),
                sql.Identifier(spec.name),
            ).as_string(conn)
            api_q_ii = (
                "SELECT * FROM q_ii(%s::text, %s::text)"
                if spec.fragment_kind == "str"
                else "SELECT * FROM q_ii(%s::text, %s::integer)"
            )

            plans = {
                "query_i_view": explain_text(cur, view_q_i, (sample_oid,)),
                "query_i_api": explain_text(cur, api_q_i, (sample_oid,)),
                "query_ii_view": explain_text(cur, view_q_ii, (value,)),
                "query_ii_api": explain_text(cur, api_q_ii, (spec.name, value)),
                "query_ii_attribute": spec.name,
                "query_ii_value": value,
            }

    ensure_results_dir()
    output_path = RESULTS_DIR / f"explain_compare_{horizontal_table}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(plans, handle, indent=2)

    print(f"EXPLAIN ANALYZE comparison written to {output_path}.")
    return plans
