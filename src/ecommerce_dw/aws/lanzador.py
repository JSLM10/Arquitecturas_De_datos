"""Corre un script de ecommerce_dw.sources con las claves de AWS ya resueltas.

    python -m ecommerce_dw.aws.lanzador generate_data --seed 42
    python -m ecommerce_dw.aws.lanzador append_batch --batch-id 1
    python -m ecommerce_dw.aws.lanzador simulate_changes --customer-id 1
"""

import runpy
import sys

from .conexiones import preparar_entorno_fuentes

PERMITIDOS = {"generate_data", "append_batch", "simulate_changes"}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in PERMITIDOS:
        sys.exit(f"Uso: python -m ecommerce_dw.aws.lanzador {{{'|'.join(sorted(PERMITIDOS))}}} [opciones]")
    nombre = sys.argv[1]
    preparar_entorno_fuentes()
    sys.argv = [nombre] + sys.argv[2:]
    runpy.run_module(f"ecommerce_dw.sources.{nombre}", run_name="__main__")


if __name__ == "__main__":
    main()
