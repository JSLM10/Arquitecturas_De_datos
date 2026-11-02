"""Tablas Parquet particionadas por fecha en S3.

Cada partición vive en una ruta fija (<tabla>/<particion>=<valor>/part-0.parquet). Reescribir una
partición pisa el mismo objeto: una reejecución nunca deja archivos duplicados, y como S3 reemplaza
cada objeto de forma atómica, Athena ve la versión anterior o la nueva completa, nunca a medias.
"""

import re

import pandas as pd

from . import s3util
from .esquemas import ESQUEMAS, PARTICIONES, RUTAS


def prefijo(tabla):
    return RUTAS[tabla] + "/"


def clave_particion(tabla, valor):
    return f"{prefijo(tabla)}{PARTICIONES[tabla]}={valor}/part-0.parquet"


def tabla_vacia(tabla):
    esquema = ESQUEMAS[tabla]
    columnas = {}
    for campo in esquema:
        if str(campo.type).startswith("timestamp"):
            columnas[campo.name] = pd.Series(dtype="datetime64[ns]")
        elif str(campo.type) == "double":
            columnas[campo.name] = pd.Series(dtype="float64")
        elif str(campo.type) in ("int32", "int64"):
            columnas[campo.name] = pd.Series(dtype="int64")
        else:
            columnas[campo.name] = pd.Series(dtype="object")
    columnas[PARTICIONES[tabla]] = pd.Series(dtype="object")
    return pd.DataFrame(columnas)


def fechas_en_ns(marco):
    """Parquet entrega microsegundos y pandas falla al concatenarlos con nanosegundos."""
    for columna in marco.columns:
        if str(marco[columna].dtype).startswith("datetime64"):
            marco[columna] = marco[columna].astype("datetime64[ns]")
    return marco


def particiones_en_s3(tabla):
    patron = re.compile(rf"{PARTICIONES[tabla]}=([^/]+)/")
    valores = set()
    for clave in s3util.listar(prefijo(tabla)):
        if clave.endswith(".parquet"):
            valores.add(patron.search(clave).group(1))
    return valores


def leer_tabla(tabla):
    particion = PARTICIONES[tabla]
    patron = re.compile(rf"{particion}=([^/]+)/")
    marcos = []
    for clave in s3util.listar(prefijo(tabla)):
        if clave.endswith(".parquet"):
            marco = fechas_en_ns(s3util.leer_parquet(clave))
            marco[particion] = patron.search(clave).group(1)
            marcos.append(marco)
    return pd.concat(marcos, ignore_index=True) if marcos else tabla_vacia(tabla)


def escribir_particiones(tabla, df, valores):
    """Reescribe solo las particiones indicadas; si una queda vacía se borra su archivo."""
    particion = PARTICIONES[tabla]
    for valor in sorted(valores):
        parte = df[df[particion] == valor]
        clave = clave_particion(tabla, valor)
        if parte.empty:
            if s3util.existe(clave):
                s3util.borrar(clave)
        else:
            s3util.escribir_parquet(clave, parte.drop(columns=[particion]), ESQUEMAS[tabla])


def borrar_tabla(tabla):
    return s3util.borrar_prefijo(prefijo(tabla))
