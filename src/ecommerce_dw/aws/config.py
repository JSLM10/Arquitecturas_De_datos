"""Variables de entorno del pipeline en AWS (sin secretos).
"""

import os

REGION = os.getenv("AWS_REGION", "us-east-2")


def requerida(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}. Corra de nuevo scripts/aws/desplegar_compadre.sh")
    return valor


def variables_requeridas():
    return [
        "DW_BUCKET",
        "RDS_ENDPOINT",
        "RDS_SECRET_ARN",
        "DOCDB_ENDPOINT",
        "DOCDB_SECRET_ARN",
        "REDSHIFT_ENDPOINT",
        "REDSHIFT_SECRET_ARN",
        "REDSHIFT_DB",
        "REDSHIFT_ROLE_ARN",
    ]
