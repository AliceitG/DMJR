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

def import_to_db(matrix, table_name, db_config):
    # Daten vorbereiten
    sparse_data = []
    for i in range(len(matrix)):
        for j in range(len(matrix[0])):
            if matrix[i][j] != 0.0:
                sparse_data.append((i + 1, j + 1, matrix[i][j]))
    
    # Verbindung und Import
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()
    
    query = f"INSERT INTO {table_name} (i, j, val) VALUES %s"
    execute_values(cursor, query, sparse_data)
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Import in {table_name} erfolgreich!")

# Tests:

if __name__ == "__main__":
    l = 10
    sparsity = 0.4

    # Matrizen generieren
    A, B = generate(l, sparsity)

    # Ausgabe zum Testen
    print("Matrix A ({} x {}):".format(len(A), len(A[0])))
    for row in A:
        print(row)

    print("\nMatrix B ({} x {}):".format(len(B), len(B[0])))
    for row in B:
        print(row)

    # DB-Konfig (** Bitte Werte anpassen **)
    db_config = {
        "dbname": "projektaufgabe1",
        "user": "projektaufgabe1_user",
        "password": "1234",
        "host": "localhost",
    }

    # Import in die Datenbank
    import_to_db(A, "A", db_config)
    import_to_db(B, "B", db_config)
