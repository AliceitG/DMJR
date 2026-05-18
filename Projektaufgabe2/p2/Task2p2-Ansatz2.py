import psycopg2

# Werte bitte anpassen!
db_config = {
        "dbname": "toydb",
        "user": "postgres",
        "password": "wortpasst",
        "host": "localhost"
    }


def ansatz2(db_config):
    """
    Ansatz 2: Matrixmultiplikation mit Vektordarstellung hier aber nur mit Array (Example 2.2 aus Lehrbuch Ding).
    Berechnet C = A * B via dotproduct(A_ROW.row, B_COL.col).
    Ergebnis nicht gespeichert.
    Return Liste von Tupeln (i, j, val) zurück.
    """
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT A_ROW.i, B_COL.j, dotproduct(A_ROW.row, B_COL.col)
        FROM A_ROW, B_COL
        WHERE dotproduct(A_ROW.row, B_COL.col) <> 0
        ORDER BY A_ROW.i, B_COL.j;
    """)

    result = cursor.fetchall()  # [(i, j, val), ...]

    cursor.close()
    conn.close()

    return result


def ansatz1(db_config): #mostly copy aus phase1
    """
    Ansatz 1: Matrixmultiplikation mit Sparse-Darstellung (Example 2.1).
    Referenzimplementierung für den Korrektheitsvergleich.
    Gibt eine Liste von Tupeln (i, j, val) zurück.
    """
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT A.i, B.j, SUM(A.val * B.val)
        FROM A, B
        WHERE A.j = B.i
        GROUP BY A.i, B.j
        ORDER BY A.i, B.j;
    """)

    result = cursor.fetchall()  # [(i, j, val), ...]

    cursor.close()
    conn.close()

    return result


def korrektheit_pruefen(db_config, toleranz=1e-6):
    """
    Vergleicht die Ergebnisse von Ansatz 1 und Ansatz 2.
    Gibt aus, ob die Ergebnisse übereinstimmen.
    """
    print("Führe Ansatz 1 aus (Sparse Representation)...")
    result1 = ansatz1(db_config)

    print("Führe Ansatz 2 aus (Vector Representation)...")
    result2 = ansatz2(db_config)

    # Als Dict für einfachen Vergleich
    dict1 = {(i, j): val for i, j, val in result1}
    dict2 = {(i, j): val for i, j, val in result2}

    alle_keys = set(dict1.keys()) | set(dict2.keys())
    fehler = []

    for key in sorted(alle_keys):
        v1 = dict1.get(key, 0.0)
        v2 = dict2.get(key, 0.0)
        if abs(v1 - v2) > toleranz:
            fehler.append((key, v1, v2))

    if not fehler:
        print(f"✓ Korrektheit bestätigt: Beide Ansätze liefern identische Ergebnisse ({len(alle_keys)} Zellen verglichen).")
    else:
        print(f"✗ Unterschiede gefunden in {len(fehler)} Zellen:")
        for (i, j), v1, v2 in fehler[:10]:  # max. 10 ausgeben
            print(f"  C[{i}][{j}]: Ansatz1={v1:.6f}, Ansatz2={v2:.6f}, Diff={abs(v1-v2):.2e}")

    return len(fehler) == 0


if __name__ == "__main__":
    #korrekt = korrektheit_pruefen(db_config)
    #if korrekt:
    #    print("\nAnsatz 2 ist korrekt implementiert.")
    #else:
    #    print("\nFehler in Ansatz 2 – bitte überprüfen.")

    print("Ergebnis Ansatz 1:")
    print(ansatz1(db_config))

    print("\nErgebnis Ansatz 2:")
    print(ansatz2(db_config))