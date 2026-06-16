import random
import psycopg2
from psycopg2.extras import execute_values

db_config = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": ""
}

def generate(l, sparsity, conn):


    if l < 2:
        raise ValueError("l muss mindestens 2 sein")
    if not (0.0 <= sparsity <= 1.0):
        raise ValueError("sparsity muss zwischen 0 und 1 liegen")


    m = l - 1
    n = l - 1

    # A: m x l
    A = [[random.uniform(1.0, 10.0) for _ in range(l)] for _ in range(m)]
    # B: l x n
    B = [[random.uniform(1.0, 10.0) for _ in range(n)] for _ in range(l)]

    total_A = m * l
    total_B = l * n

    zeros_in_A = round(sparsity * total_A)
    zeros_in_B = round(sparsity * total_B)

    positions_A = [(i, j) for i in range(m) for j in range(l)]
    positions_B = [(i, j) for i in range(l) for j in range(n)]

    random.shuffle(positions_A)
    random.shuffle(positions_B)


    for i, j in positions_A[:zeros_in_A]:
        A[i][j] = 0.0
    for i, j in positions_B[:zeros_in_B]:
        B[i][j] = 0.0

    return A, B

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
    cursor.execute("SELECT MAX(i), MAX(j) FROM A;")
    m, l = cursor.fetchone()  # A ist m x l

    cursor.execute("SELECT MAX(i), MAX(j) FROM B;")
    _, n = cursor.fetchone()  # B ist l x n

    # Sparse-Werte aus a und b lesen
    cursor.execute("SELECT i, j, val FROM A;")
    a_vals = {(i, j): val for i, j, val in cursor.fetchall()}

    cursor.execute("SELECT i, j, val FROM B;")
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
