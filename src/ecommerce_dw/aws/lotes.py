"""Control de lotes: tabla ops.lotes en Redshift.

Estados de un lote (marca de avance): extraido -> cargado -> procesado.
El campo error guarda el ultimo fallo sin cambiar el estado. La marca de avance de un lote
solo la usa el siguiente si quedo cargado o procesado.
"""

import re
from datetime import datetime, timezone

DDL_ESTRUCTURA = [
    # "raw" es palabra reservada de Redshift: SIEMPRE va entre comillas.
    'create schema if not exists "raw"',
    "create schema if not exists ops",
    """create table if not exists ops.lotes (
        batch_id varchar(32) not null,
        entidad varchar(40) not null,
        fuente varchar(16),
        modo varchar(16),
        estado varchar(16),
        filas_extraidas bigint,
        filas_cargadas bigint,
        marca_inferior varchar(64),
        marca_superior varchar(64),
        archivo_s3 varchar(512),
        extraido_en timestamp,
        cargado_en timestamp,
        procesado_en timestamp,
        error varchar(1500)
    )""",
]

_PATRON_BATCH = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def nuevo_batch_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def validar_batch_id(batch_id):
    if not _PATRON_BATCH.match(batch_id or ""):
        raise ValueError(f"batch_id invalido: {batch_id!r} (solo letras, numeros, guion y guion bajo; maximo 32)")
    return batch_id


def ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def marca_previa(cursor, entidad):
    """Marca de avance del ultimo lote cargado de esa entidad, o None si es la primera vez."""
    cursor.execute(
        "select marca_superior from ops.lotes "
        "where entidad = %s and estado in ('cargado', 'procesado') and marca_superior is not null "
        "order by batch_id desc limit 1",
        (entidad,),
    )
    fila = cursor.fetchone()
    return int(fila[0]) if fila else None


def guardar(cursor, batch_id, entidad, **campos):
    asignaciones = ", ".join(f"{nombre} = %s" for nombre in campos)
    cursor.execute(
        f"update ops.lotes set {asignaciones} where batch_id = %s and entidad = %s",
        [*campos.values(), batch_id, entidad],
    )
    if cursor.rowcount == 0:
        columnas = ["batch_id", "entidad", *campos]
        marcadores = ", ".join(["%s"] * len(columnas))
        cursor.execute(
            f"insert into ops.lotes ({', '.join(columnas)}) values ({marcadores})",
            [batch_id, entidad, *campos.values()],
        )


def marcar_error(cursor, batch_id, mensaje):
    cursor.execute(
        "update ops.lotes set error = %s where batch_id = %s and (estado <> 'procesado' or estado is null)",
        (mensaje[:1400], batch_id),
    )
