import psycopg2
from psycopg2.extras import execute_values

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "",
    "host": "localhost"
}


def create_tables(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS A_ROW;")
    cursor.execute("DROP TABLE IF EXISTS B_COL;")
    cursor.execute("""
        CREATE TABLE A_ROW (
            i INT NOT NULL,
            row DOUBLE PRECISION[] NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE B_COL (
            j INT NOT NULL,
            col DOUBLE PRECISION[] NOT NULL
        );
    """)
    conn.commit()
    cursor.close()


def import_from_sparse(conn):
    cursor = conn.cursor()

    # Dimensionen ermitteln
    cursor.execute("SELECT MAX(i), MAX(j) FROM a;")
    m, l = cursor.fetchone()  # A ist m x l

    cursor.execute("SELECT MAX(i), MAX(j) FROM b;")
    _, n = cursor.fetchone()  # B ist l x n

    # Sparse-Werte aus a und b lesen
    cursor.execute("SELECT i, j, val FROM a;")
    a_vals = {(i, j): val for i, j, val in cursor.fetchall()}

    cursor.execute("SELECT i, j, val FROM b;")
    b_vals = {(i, j): val for i, j, val in cursor.fetchall()}

    # A zeilenweise aufbauen (fehlende Einträge = 0)
    data_A = []
    for i in range(1, m + 1):
        row = [float(a_vals.get((i, j), 0)) for j in range(1, l + 1)]
        data_A.append((i, row))

    # B spaltenweise aufbauen
    data_B = []
    for j in range(1, n + 1):
        col = [float(b_vals.get((i, j), 0)) for i in range(1, l + 1)]
        data_B.append((j, col))

    execute_values(cursor, "INSERT INTO A_ROW (i, row) VALUES %s", data_A)
    execute_values(cursor, "INSERT INTO B_COL (j, col) VALUES %s", data_B)

    conn.commit()
    cursor.close()


if __name__ == "__main__":
    conn = psycopg2.connect(**db_config)
    create_tables(conn)
    import_from_sparse(conn)
    conn.close()
    print("Import für Ansatz 2 erfolgreich!")
