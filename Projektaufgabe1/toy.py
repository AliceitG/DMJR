from db_utils import compare_relations, connect_db, drop_relation


def setup_toy_example():
    with connect_db() as conn:
        with conn.cursor() as cur:
            drop_relation(cur, "h2v_toy", "VIEW")
            drop_relation(cur, "v_toy_all", "VIEW")
            drop_relation(cur, "v_toy_oids", "TABLE")
            drop_relation(cur, "v_toy_str", "TABLE")
            drop_relation(cur, "v_toy_int", "TABLE")
            drop_relation(cur, "v_toy", "TABLE")
            drop_relation(cur, "h_toy", "TABLE")

            cur.execute(
                """
                CREATE TABLE h_toy (
                    oid INTEGER PRIMARY KEY,
                    a1 TEXT,
                    a2 TEXT,
                    a3 INTEGER
                );
                """
            )
            cur.execute(
                """
                INSERT INTO h_toy (oid, a1, a2, a3) VALUES
                (1, 'a', 'b', NULL),
                (2, NULL, 'c', 2),
                (3, NULL, NULL, 3),
                (4, NULL, NULL, NULL);
                """
            )

            cur.execute(
                """
                CREATE TABLE v_toy (
                    oid INTEGER NOT NULL,
                    "key" TEXT NOT NULL,
                    val TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                INSERT INTO v_toy (oid, "key", val) VALUES
                (1, 'a1', 'a'),
                (1, 'a2', 'b'),
                (2, 'a2', 'c'),
                (2, 'a3', '2'),
                (3, 'a3', '3');
                """
            )

            cur.execute(
                """
                CREATE TABLE v_toy_oids (
                    oid INTEGER NOT NULL
                );
                """
            )
            cur.execute("INSERT INTO v_toy_oids (oid) SELECT oid FROM h_toy ORDER BY oid;")

            cur.execute(
                """
                CREATE TABLE v_toy_str (
                    oid INTEGER NOT NULL,
                    "key" TEXT NOT NULL,
                    val TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE v_toy_int (
                    oid INTEGER NOT NULL,
                    "key" TEXT NOT NULL,
                    val INTEGER NOT NULL
                );
                """
            )
            cur.execute(
                """
                INSERT INTO v_toy_str (oid, "key", val)
                SELECT oid, "key", val
                FROM v_toy
                WHERE "key" IN ('a1', 'a2');
                """
            )
            cur.execute(
                """
                INSERT INTO v_toy_int (oid, "key", val)
                SELECT oid, "key", val::integer
                FROM v_toy
                WHERE "key" = 'a3';
                """
            )

            cur.execute(
                """
                CREATE VIEW v_toy_all AS
                SELECT oid, "key", val::text AS val
                FROM v_toy_str
                UNION ALL
                SELECT oid, "key", val::text AS val
                FROM v_toy_int;
                """
            )

            cur.execute(
                """
                CREATE VIEW h2v_toy AS
                SELECT
                    o.oid,
                    a1.val AS a1,
                    a2.val AS a2,
                    a3.val AS a3
                FROM v_toy_oids AS o
                LEFT JOIN v_toy_str AS a1
                    ON o.oid = a1.oid AND a1."key" = 'a1'
                LEFT JOIN v_toy_str AS a2
                    ON o.oid = a2.oid AND a2."key" = 'a2'
                LEFT JOIN v_toy_int AS a3
                    ON o.oid = a3.oid AND a3."key" = 'a3'
                ORDER BY o.oid;
                """
            )

    print("Toy example created: h_toy, v_toy, v_toy_str, v_toy_int, v_toy_all, h2v_toy.")


def test_toy_correctness():
    is_equal, _, _ = compare_relations("h_toy", "h2v_toy", "Toy V2H correctness")
    return is_equal
