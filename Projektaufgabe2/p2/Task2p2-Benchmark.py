import time
import random
import psycopg2
from psycopg2.extras import execute_values
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

db_config = {
    "dbname": "projektaufgabe1",
    "user": "projektaufgabe1_user",
    "password": "",
    "host": "localhost"
}

L_VALUES = [8, 16, 32, 64, 128, 256]
S_VALUES = [0.1, 0.3, 0.5, 0.7, 0.9]
REPEATS = 3


def generate(l, sparsity):
    m, n = l - 1, l - 1
    A = [[random.uniform(1.0, 10.0) for _ in range(l)] for _ in range(m)]
    B = [[random.uniform(1.0, 10.0) for _ in range(n)] for _ in range(l)]
    pos_A = [(i, j) for i in range(m) for j in range(l)]
    pos_B = [(i, j) for i in range(l) for j in range(n)]
    random.shuffle(pos_A)
    random.shuffle(pos_B)
    for i, j in pos_A[:round(sparsity * m * l)]:
        A[i][j] = 0.0
    for i, j in pos_B[:round(sparsity * l * n)]:
        B[i][j] = 0.0
    return A, B


def setup_db(conn, A, B):
    cursor = conn.cursor()
    m, l = len(A), len(A[0])
    n = len(B[0])

    cursor.execute("DELETE FROM a;")
    cursor.execute("DELETE FROM b;")
    sparse_A = [(i+1, j+1, A[i][j]) for i in range(m) for j in range(l) if A[i][j] != 0.0]
    sparse_B = [(i+1, j+1, B[i][j]) for i in range(l) for j in range(n) if B[i][j] != 0.0]
    if sparse_A:
        execute_values(cursor, "INSERT INTO a (i, j, val) VALUES %s", sparse_A)
    if sparse_B:
        execute_values(cursor, "INSERT INTO b (i, j, val) VALUES %s", sparse_B)

    cursor.execute("DELETE FROM A_ROW;")
    cursor.execute("DELETE FROM B_COL;")
    data_A_ROW = [(i+1, [float(A[i][j]) for j in range(l)]) for i in range(m)]
    data_B_COL = [(j+1, [float(B[i][j]) for i in range(l)]) for j in range(n)]
    execute_values(cursor, "INSERT INTO A_ROW (i, row) VALUES %s", data_A_ROW)
    execute_values(cursor, "INSERT INTO B_COL (j, col) VALUES %s", data_B_COL)

    conn.commit()
    cursor.close()


def ansatz0(conn):
    cursor = conn.cursor()
    # Dimensionen aus Vektortabellen lesen (immer vollständig, auch bei hoher Sparsity)
    cursor.execute("SELECT MAX(i) FROM A_ROW;")
    m = cursor.fetchone()[0]
    cursor.execute("SELECT array_length(row, 1) FROM A_ROW LIMIT 1;")
    l = cursor.fetchone()[0]
    cursor.execute("SELECT MAX(j) FROM B_COL;")
    n = cursor.fetchone()[0]
    cursor.execute("SELECT i, j, val FROM a;")
    a_sparse = cursor.fetchall()
    cursor.execute("SELECT i, j, val FROM b;")
    b_sparse = cursor.fetchall()
    cursor.close()

    A = [[0.0] * l for _ in range(m)]
    B = [[0.0] * n for _ in range(l)]
    for i, j, v in a_sparse:
        A[i-1][j-1] = float(v)
    for i, j, v in b_sparse:
        B[i-1][j-1] = float(v)

    C = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for k in range(l):
            if A[i][k] == 0.0:
                continue
            for j in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C


def ansatz1(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT A.i, B.j, SUM(A.val * B.val)
        FROM a A, b B
        WHERE A.j = B.i
        GROUP BY A.i, B.j
        ORDER BY A.i, B.j;
    """)
    result = cursor.fetchall()
    cursor.close()
    return result


def ansatz2(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT A_ROW.i, B_COL.j, dotproduct(A_ROW.row, B_COL.col) AS val
        FROM A_ROW, B_COL
        ORDER BY A_ROW.i, B_COL.j;
    """)
    result = cursor.fetchall()
    cursor.close()
    return result


def measure(func, repeats):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        func()
        times.append(time.perf_counter() - t0)
    return sum(times) / len(times)


def run_benchmark():
    conn = psycopg2.connect(**db_config)
    results = {}
    total = len(L_VALUES) * len(S_VALUES)
    done = 0

    for l in L_VALUES:
        for s in S_VALUES:
            done += 1
            print(f"[{done}/{total}] L={l:3d}, S={s:.1f} ...", end=" ", flush=True)
            A, B = generate(l, s)
            setup_db(conn, A, B)

            t0 = measure(lambda: ansatz0(conn), REPEATS)
            t1 = measure(lambda: ansatz1(conn), REPEATS)
            t2 = measure(lambda: ansatz2(conn), REPEATS)

            results[(l, s, 0)] = t0
            results[(l, s, 1)] = t1
            results[(l, s, 2)] = t2

            print(f"A0={t0:.3f}s  A1={t1:.3f}s  A2={t2:.3f}s")

    conn.close()
    return results


def plot_results(results):
    colors  = {0: 'tab:blue', 1: 'tab:orange', 2: 'tab:green'}
    labels  = {0: 'Ansatz 0 (Python)', 1: 'Ansatz 1 (Sparse SQL)', 2: 'Ansatz 2 (Vector SQL)'}
    markers = {0: 'o', 1: 's', 2: '^'}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Zeit vs. L (Mittelwert über alle S-Werte)
    ax = axes[0]
    for ansatz in [0, 1, 2]:
        means = np.array([np.mean([results[(l, s, ansatz)] for s in S_VALUES]) for l in L_VALUES])
        stds  = np.array([np.std( [results[(l, s, ansatz)] for s in S_VALUES]) for l in L_VALUES])
        ax.plot(L_VALUES, means, color=colors[ansatz], label=labels[ansatz],
                marker=markers[ansatz], linewidth=2)
        ax.fill_between(L_VALUES, means - stds, means + stds,
                        color=colors[ansatz], alpha=0.15)

    ax.set_xlabel('L (Matrixgröße)', fontsize=12)
    ax.set_ylabel('Ø Zeit pro Multiplikation (s)', fontsize=12)
    ax.set_title('Laufzeit vs. L\n(gemittelt über alle Sparsity-Werte)', fontsize=12)
    ax.set_yscale('log')
    ax.set_xscale('log', base=2)
    ax.set_xticks(L_VALUES)
    ax.set_xticklabels(L_VALUES)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 2: Zeit vs. S (größtes L)
    ax = axes[1]
    fixed_l = L_VALUES[-1]
    for ansatz in [0, 1, 2]:
        vals = [results[(fixed_l, s, ansatz)] for s in S_VALUES]
        ax.plot(S_VALUES, vals, color=colors[ansatz], label=labels[ansatz],
                marker=markers[ansatz], linewidth=2)

    ax.set_xlabel('Sparsity S', fontsize=12)
    ax.set_ylabel('Ø Zeit pro Multiplikation (s)', fontsize=12)
    ax.set_title(f'Laufzeit vs. Sparsity S\n(L={fixed_l})', fontsize=12)
    ax.set_yscale('log')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = 'results.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    print(f"\nGrafik gespeichert: {out}")


if __name__ == "__main__":
    print("=== Benchmark ===")
    print(f"L-Werte : {L_VALUES}")
    print(f"S-Werte : {S_VALUES}")
    print(f"Repeats : {REPEATS}\n")

    results = run_benchmark()

    print("\n=== Zusammenfassung ===")
    for l in L_VALUES:
        for s in S_VALUES:
            print(f"L={l:3d}, S={s:.1f}:  "
                  f"A0={results[(l,s,0)]:.4f}s  "
                  f"A1={results[(l,s,1)]:.4f}s  "
                  f"A2={results[(l,s,2)]:.4f}s")

    plot_results(results)
    print("=== Ende ===")
