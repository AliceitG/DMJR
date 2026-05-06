import psycopg2


def ansatz1(cursor):
    """Sparse Matrix Multiplication via SQL im DBMS.
    Ergebnis C wird nicht persistent gespeichert."""
    cursor.execute("""
        SELECT A.i, B.j, SUM(A.val * B.val)
        FROM A, B
        WHERE A.j = B.i
        GROUP BY A.i, B.j
        ORDER BY A.i, B.j;
    """)
    return cursor.fetchall()

'''Beispiel
A = 1 0  B = 3 0
    0 2      0 4
    
A = (1,1,1), (2,2,2)
B = (1,1,3), (2,2,4)'''


# TODO andere Nutzer bitte DB-Angaben anpassen
db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "1234",
    "host": "localhost"
}

conn = psycopg2.connect(**db_config)
cur = conn.cursor()

rows = ansatz1(cur)

print("Ansatz 1 – Ergebnis (i, j, val):")
for row in rows:
    print(row)

cur.close()
conn.close()
