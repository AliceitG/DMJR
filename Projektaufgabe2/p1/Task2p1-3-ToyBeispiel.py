import psycopg2

# A 4x3
a = [
    [1, 0, 3],
    [0, 7, 8],
    [9, 8, 0],
    [4, 0, 2]
]

# B 3x5
b = [
    [5, 0, 7, 10, 4],
    [8, 9, 1, 0, 8],
    [4, 0, 0, 2, 1]
]

""" C 4x5
    c = a x b 
    Ausgerechnet: 
    c = [
        [17, 0, 7, 16, 7],
        [88, 63, 7, 16, 64],
        [109, 72, 71, 90, 100],
        [28, 0, 28, 44, 18]
    ]
"""


def import_matrix(matrix, table_name, cursor):
    """Importiert eine Matrix als Sparse-Darstellung (i, j, val) in die DB.
    Nur Non-Zero Werte werden gespeichert."""

    cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
    cursor.execute(f"CREATE TABLE {table_name} (i INT, j INT, val DOUBLE PRECISION);")

    for i in range(len(matrix)):
        for j in range(len(matrix[0])):
            if matrix[i][j] != 0:
                cursor.execute(
                    f"INSERT INTO {table_name} (i, j, val) VALUES (%s, %s, %s);",
                    (i + 1, j + 1, matrix[i][j])
                )

    print(f"Import to {table_name} done")


# Setup TODO andere nutzer bitte angaben ändern
conn = psycopg2.connect(
    dbname="toydb",
    user="postgres",
    password="wortpasst",
    host="localhost"
)
cur = conn.cursor()

# Import
import_matrix(a, "A", cur)
import_matrix(b, "B", cur)

# Test
for table in ["A", "B"]:
    cur.execute(f"SELECT * FROM {table} ORDER BY i, j;")
    rows = cur.fetchall()
    print(f"\nTabelle {table}:")
    for r in rows:
        print(r)

conn.commit()
cur.close()
conn.close()