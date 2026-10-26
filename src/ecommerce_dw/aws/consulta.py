"""Corre una consulta SQL en Redshift e imprime el resultado como tabla de texto.

    python -m ecommerce_dw.aws.consulta "select count(*) from marts.fct_sales"
"""

import sys

from .conexiones import conectar_redshift


def _texto(valor):
    return valor.decode() if isinstance(valor, bytes) else str(valor)


def main():
    if len(sys.argv) < 2:
        sys.exit('Uso: python -m ecommerce_dw.aws.consulta "select ..."')
    conexion = conectar_redshift()
    try:
        cursor = conexion.cursor()
        cursor.execute(" ".join(sys.argv[1:]))
        if cursor.description is None:
            conexion.commit()
            print("OK")
            return
        columnas = [_texto(columna[0]) for columna in cursor.description]
        filas = [["NULL" if valor is None else _texto(valor) for valor in fila] for fila in cursor.fetchall()]
    finally:
        conexion.close()

    anchos = [max(len(columnas[i]), *(len(fila[i]) for fila in filas)) if filas else len(columnas[i]) for i in range(len(columnas))]
    linea = " | ".join(columnas[i].ljust(anchos[i]) for i in range(len(columnas)))
    print(linea)
    print("-+-".join("-" * ancho for ancho in anchos))
    for fila in filas:
        print(" | ".join(fila[i].ljust(anchos[i]) for i in range(len(columnas))))
    print(f"({len(filas)} filas)")


if __name__ == "__main__":
    main()
