#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define N 1024

/* Matrix multiply: A * B -> C */
void matmul(double A[N][N], double B[N][N], double C[N][N]) {
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++)
            for (int k = 0; k < N; k++)
                C[i][j] += A[i][k] * B[k][j];
}

/* Bubble sort on a random array */
void bubblesort(int *arr, int n) {
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - i - 1; j++)
            if (arr[j] > arr[j + 1]) {
                int tmp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = tmp;
            }
}

int main(void) {
    /* Stack-allocate matrices */
    static double A[N][N], B[N][N], C[N][N];

    /* Init with simple pattern */
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++) {
            A[i][j] = (double)(i + j + 1);
            B[i][j] = (double)(i - j + 1);
        }

    matmul(A, B, C);
    printf("C[0][0] = %.2f\n", C[0][0]);

    /* Bubble sort a small array to add branch activity */
    int arr[4096];
    for (int i = 0; i < 4096; i++)
        arr[i] = rand() % 10000;
    bubblesort(arr, 4096);
    printf("sorted[0]=%d sorted[4095]=%d\n", arr[0], arr[4095]);

    return 0;
}
