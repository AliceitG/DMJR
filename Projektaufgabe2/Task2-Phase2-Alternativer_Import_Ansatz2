import random
import psycopg2
from psycopg2.extras import execute_values

def generate(l, sparsity):
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

def import_rows_and_cols(A, B, db_config):
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    data_A = []
    for i in range(len(A)):
        data_A.append((i + 1, A[i]))   # ganze Zeile speichern

    data_B = []
    for j in range(len(B[0])):
        col = [B[i][j] for i in range(len(B))]
        data_B.append((j + 1, col))    # ganze Spalte speichern

    execute_values(cursor, "INSERT INTO A_ROW (i, row) VALUES %s", data_A)
    execute_values(cursor, "INSERT INTO B_COL (j, col) VALUES %s", data_B)

    conn.commit()
    cursor.close()
    conn.close()

# Test

if __name__ == "__main__":
    l = 10
    sparsity = 0.4

    A, B = generate(l, sparsity)

# Werte bitte anpassen!
    db_config = {
        "dbname": "postgres",
        "user": "nargiz",
        "password": "...",
        "host": "localhost"
    }

    import_rows_and_cols(A, B, db_config)
    print("Import für Ansatz 2 erfolgreich!")
