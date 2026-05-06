import psycopg2

# Toy-Beispiel
a = [
    [1, 0, 3],
    [0, 7, 8],
    [9, 8, 0],
    [4, 0, 2]
]

b = [
    [5, 0, 7, 10, 4],
    [8, 9, 1,  0, 8],
    [4, 0, 0,  2, 1]
]

# Erwartetes Ergebnis (von Hand berechnet)
c_expected = [
    [ 17,  0,  7, 16,   7],
    [ 88, 63,  7, 16,  64],
    [109, 72, 71, 90, 100],
    [ 28,  0, 28, 44,  18]
]


def matrixmult(A, B):
    """Ansatz 0: klassischer i-k-j Algorithmus, O(m*l*n)."""
    m = len(A)
    l = len(A[0])
    n = len(B[0])
    C = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for k in range(l):
            for j in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C


def sparse_to_matrix(rows, m, n):
    """Konvertiert SQL-Ergebnis (i, j, val) in eine 2D-Liste (0-basiert)."""
    C = [[0.0] * n for _ in range(m)]
    for i, j, val in rows:
        C[i - 1][j-1] = float(val)
    return C


# TODO andere Nutzer bitte DB-Angaben anpassen
db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost"
}

m, n = len(a), len(b[0])
c_exp_float = [[float(v) for v in row] for row in c_expected]

# --- Ansatz 0 ---
c0 = matrixmult(a, b)
print("Ansatz 0 (Client-seitig):")
for row in c0:
    print(row)

# --- Ansatz 1 ---
conn = psycopg2.connect(**db_config)
cur = conn.cursor()
cur.execute("""
    SELECT A.i, B.j, SUM(A.val * B.val)
    FROM A, B
    WHERE A.j = B.i
    GROUP BY A.i, B.j
    ORDER BY A.i, B.j;
""")
rows = cur.fetchall()
cur.close()
conn.close()

c1 = sparse_to_matrix(rows, m, n)
print("\nAnsatz 1 (SQL im DBMS):")
for row in c1:
    print(row)

# --- Korrektheitsprüfung ---
print("\n--- Korrektheitsprüfung ---")
print("Ansatz 0 == erwartet:", c0 == c_exp_float)
print("Ansatz 1 == erwartet:", c1 == c_exp_float)
print("Ansatz 0 == Ansatz 1:", c0 == c1)
