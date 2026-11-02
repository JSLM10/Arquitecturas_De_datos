"""Registro de tablas y particiones en el catálogo de Glue.

Las tablas las crea Terraform. Cuando aparece una fecha nueva en S3, esta tarea registra la partición;
sin ese paso Athena no la ve. También quita las particiones cuyos archivos ya no existen.
"""

import copy
import logging

import boto3

from . import config, tablas
from .esquemas import ESQUEMAS, PARTICIONES, RUTAS, tipo_glue

LOGGER = logging.getLogger(__name__)


def _glue():
    return boto3.client("glue", region_name=config.REGION)


def verificar_columnas(tabla, definicion):
    esperado = [(c.name, tipo_glue(c.type)) for c in ESQUEMAS[tabla]]
    real = [(c["Name"], c["Type"]) for c in definicion["StorageDescriptor"]["Columns"]]
    if esperado != real:
        raise ValueError(f"{tabla}: las columnas de Glue {real} no coinciden con el Parquet {esperado}")


def particiones_registradas(glue, tabla):
    valores = set()
    for pagina in glue.get_paginator("get_partitions").paginate(DatabaseName=config.base_datos(), TableName=tabla):
        valores.update(p["Values"][0] for p in pagina["Partitions"])
    return valores


def sincronizar():
    glue = _glue()
    resumen = {}
    for tabla in ESQUEMAS:
        definicion = glue.get_table(DatabaseName=config.base_datos(), Name=tabla)["Table"]
        verificar_columnas(tabla, definicion)
        en_s3 = tablas.particiones_en_s3(tabla)
        en_glue = particiones_registradas(glue, tabla)
        faltan, sobran = sorted(en_s3 - en_glue), sorted(en_glue - en_s3)

        for inicio in range(0, len(faltan), 100):
            entradas = []
            for valor in faltan[inicio : inicio + 100]:
                descriptor = copy.deepcopy(definicion["StorageDescriptor"])
                descriptor["Location"] = f"s3://{config.bucket()}/{RUTAS[tabla]}/{PARTICIONES[tabla]}={valor}/"
                entradas.append({"Values": [valor], "StorageDescriptor": descriptor})
            glue.batch_create_partition(DatabaseName=config.base_datos(), TableName=tabla, PartitionInputList=entradas)
        for inicio in range(0, len(sobran), 25):
            glue.batch_delete_partition(
                DatabaseName=config.base_datos(), TableName=tabla,
                PartitionsToDelete=[{"Values": [v]} for v in sobran[inicio : inicio + 25]],
            )
        resumen[tabla] = {"agregadas": len(faltan), "eliminadas": len(sobran), "total": len(en_s3)}
    LOGGER.info("Glue: %s", resumen)
    return resumen
