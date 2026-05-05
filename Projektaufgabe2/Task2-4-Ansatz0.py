import numpy as np

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


def matrixmult(A, B):
    """C = A x B auf Client-Seite (also reine Mathe??? fehlt da was???)"""

    m = len(A)
    l = len(A[0])
    n = len(B[0])

    C = [[0] * n for _ in range(m)]

    for i in range(m):
        for k in range(l):
            for j in range(n):
                C[i][j] += A[i][k] * B[k][j]

    return C


# Test mit Toy-Beispiel
c_result = matrixmult(a, b)

print("\nErgebnis C = A x B (Ansatz 0):")
for row in c_result:
    print(row)