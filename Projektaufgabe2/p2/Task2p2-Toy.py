import psycopg2
import pandas as pd

db_config = {
    "dbname": "toydb",
    "user": "postgres",
    "password": "wortpasst",
    "host": "localhost"
}

conn = psycopg2.connect(**db_config)
cursor = conn.cursor()


cursor.execute("""
        SELECT A_ROW.i, B_COL.j, dotproduct(A_ROW.row, B_COL.col) AS val
        FROM A_ROW, B_COL
        WHERE dotproduct(A_ROW.row, B_COL.col) <> 0
        ORDER BY A_ROW.i, B_COL.j;
    """)

result = cursor.fetchall()  # [(i, j, val), ...]

df = pd.DataFrame(result, columns=["i", "j", "val"])
matrix = df.pivot(index="i", columns="j", values="val").values

print(matrix)

#for row in result:
#    print(row)

cursor.close()
conn.close()