"""Carga de lotes de S3 a las tablas raw con COPY.

Es idempotente: borra las filas del lote antes del COPY, dentro de la misma transaccion.
"""

import logging

from .config import REGION, requerida
from .entidades import ENTIDADES, tabla_raw
from .extraccion import clave_datos

LOGGER = logging.getLogger(__name__)


def ddl_tabla(nombre):
    columnas = ", ".join(f"{columna} {tipo}" for columna, tipo in ENTIDADES[nombre]["columnas"])
    return (
        f"create table if not exists {tabla_raw(nombre)} ("
        f"{columnas}, _batch_id varchar(32), _source varchar(64), _loaded_at timestamp default getdate())"
    )


def asegurar_tablas(cursor):
    for nombre in ENTIDADES:
        cursor.execute(ddl_tabla(nombre))


def sql_copy(nombre, batch_id):
    columnas = ", ".join(columna for columna, _ in ENTIDADES[nombre]["columnas"]) + ", _batch_id, _source"
    return (
        f"COPY {tabla_raw(nombre)} ({columnas}) "
        f"FROM 's3://{requerida('DW_BUCKET')}/{clave_datos(batch_id, nombre)}' "
        f"IAM_ROLE '{requerida('REDSHIFT_ROLE_ARN')}' "
        f"FORMAT AS CSV IGNOREHEADER 1 GZIP TIMEFORMAT 'auto' DATEFORMAT 'auto' "
        f"EMPTYASNULL BLANKSASNULL REGION '{REGION}'"
    )


def cargar_entidad(cursor, nombre, batch_id, esperadas):
    """Borra el lote si ya estaba, hace COPY y verifica el conteo. Devuelve las filas cargadas."""
    tabla = tabla_raw(nombre)
    cursor.execute(f"delete from {tabla} where _batch_id = %s", (batch_id,))
    cursor.execute(sql_copy(nombre, batch_id))
    cursor.execute(f"select count(*) from {tabla} where _batch_id = %s", (batch_id,))
    cargadas = cursor.fetchone()[0]
    if cargadas != esperadas:
        raise ValueError(f"{nombre}: el manifiesto dice {esperadas} filas y raw quedo con {cargadas}")
    LOGGER.info("[lote=%s entidad=%s] COPY ok: %s filas en %s", batch_id, nombre, cargadas, tabla)
    return cargadas
