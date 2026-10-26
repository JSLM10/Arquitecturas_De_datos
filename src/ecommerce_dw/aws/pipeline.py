"""Tareas del DAG de AWS. Cada funcion es una etapa y deja el lote y la tarea en el log.
"""

import logging
import os

import boto3

from .carga import asegurar_tablas, cargar_entidad
from .config import REGION, requerida, variables_requeridas
from .conexiones import conectar_redshift, preparar_entorno_fuentes
from .entidades import ENTIDADES, entidades_de
from .extraccion import extraer_entidad, leer_manifiesto
from .lotes import (
    DDL_ESTRUCTURA,
    ahora,
    guardar,
    marca_previa,
    marcar_error,
    nuevo_batch_id,
    validar_batch_id,
)

LOGGER = logging.getLogger(__name__)
MODOS = ("auto", "completo", "incremental")


def _registrar(lote, tarea, mensaje, *argumentos):
    LOGGER.info("[lote=%s tarea=%s] " + mensaje, lote, tarea, *argumentos)


def validar_configuracion(reprocesar_lote=None, modo="auto", simular_fallo=None):
    """Etapa 1: valida variables, accesos y estructura. Devuelve el contexto del lote."""
    faltan = [nombre for nombre in variables_requeridas() if not os.getenv(nombre)]
    if faltan:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(faltan)}")
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}, no {modo!r}")

    reprocesar = bool(reprocesar_lote)
    batch_id = validar_batch_id(reprocesar_lote if reprocesar else nuevo_batch_id())
    tarea = "validar_configuracion"

    boto3.client("s3", region_name=REGION).head_bucket(Bucket=requerida("DW_BUCKET"))
    _registrar(batch_id, tarea, "S3 ok (bucket %s)", requerida("DW_BUCKET"))

    conexion = conectar_redshift()
    try:
        cursor = conexion.cursor()
        cursor.execute("select 1")
        for sentencia in DDL_ESTRUCTURA:
            cursor.execute(sentencia)
        asegurar_tablas(cursor)
        conexion.commit()
    finally:
        conexion.close()
    _registrar(batch_id, tarea, "Redshift ok y estructura (raw, ops) lista")

    if reprocesar:
        # Reprocesar no toca las fuentes: solo hace falta que el lote este completo en S3.
        for nombre in ENTIDADES:
            leer_manifiesto(batch_id, nombre)
        _registrar(batch_id, tarea, "Lote %s completo en S3: se reprocesa sin consultar las fuentes", batch_id)
    else:
        _probar_fuentes(batch_id, tarea)

    if simular_fallo:
        _registrar(batch_id, tarea, "OJO: esta corrida va a fallar a proposito en %s (escenario de fallo controlado)", simular_fallo)
    return {"batch_id": batch_id, "reprocesar": reprocesar, "modo": modo, "simular_fallo": simular_fallo}


def _probar_fuentes(batch_id, tarea):
    from pymongo import MongoClient

    from ecommerce_dw.ingestion.raw_sources import connect_mysql

    preparar_entorno_fuentes()
    conexion = connect_mysql()
    try:
        cursor = conexion.cursor()
        cursor.execute("select 1")
        cursor.fetchall()
    finally:
        conexion.close()
    cliente = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=10000)
    try:
        cliente.admin.command("ping")
    finally:
        cliente.close()
    _registrar(batch_id, tarea, "RDS MySQL y DocumentDB responden")


def extraer_fuente(fuente, contexto):
    """Etapas 2 y 3: extrae una fuente a S3. Con reprocesar no consulta las fuentes."""
    batch_id, reprocesar, modo = contexto["batch_id"], contexto["reprocesar"], contexto["modo"]
    tarea = f"extraer_{fuente}"
    if not reprocesar:
        preparar_entorno_fuentes()

    resumen = {}
    conexion = conectar_redshift()
    try:
        cursor = conexion.cursor()
        for nombre in entidades_de(fuente):
            if reprocesar:
                manifiesto = leer_manifiesto(batch_id, nombre)
                _registrar(batch_id, tarea, "%s: %s filas ya estan en S3 (no se consulta la fuente)", nombre, manifiesto["filas"])
            else:
                previa = marca_previa(cursor, nombre) if modo != "completo" else None
                manifiesto = extraer_entidad(nombre, batch_id, "incremental" if previa is not None else "completo", previa)
                guardar(
                    cursor, batch_id, nombre,
                    fuente=fuente, modo=manifiesto["modo"], estado="extraido",
                    filas_extraidas=manifiesto["filas"],
                    marca_inferior=None if manifiesto["marca_inferior"] is None else str(manifiesto["marca_inferior"]),
                    marca_superior=None if manifiesto["marca_superior"] is None else str(manifiesto["marca_superior"]),
                    archivo_s3=manifiesto["archivo"], extraido_en=ahora(), error=None,
                )
                conexion.commit()
            resumen[nombre] = {"filas": manifiesto["filas"], "modo": manifiesto["modo"]}
    finally:
        conexion.close()
    return resumen


def cargar_lote(contexto):
    """Etapa 4: COPY de todas las entidades del lote en una sola transaccion."""
    batch_id = contexto["batch_id"]
    tarea = "cargar_a_redshift"
    cargadas = {}
    conexion = conectar_redshift()
    try:
        cursor = conexion.cursor()
        try:
            for nombre in ENTIDADES:
                esperadas = leer_manifiesto(batch_id, nombre)["filas"]
                cargadas[nombre] = cargar_entidad(cursor, nombre, batch_id, esperadas)
            if contexto.get("simular_fallo") == "cargar_a_redshift":
                # Fallo controlado: los COPY ya corrieron pero NO se confirman. El rollback deja raw intacto.
                raise RuntimeError(f"Fallo controlado en cargar_a_redshift (lote {batch_id}): se deshace la carga completa")
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        for nombre, filas in cargadas.items():
            guardar(cursor, batch_id, nombre, estado="cargado", filas_cargadas=filas, cargado_en=ahora(), error=None)
        conexion.commit()
    finally:
        conexion.close()
    _registrar(batch_id, tarea, "Lote cargado: %s", cargadas)
    return cargadas


def registrar_resultado(contexto):
    """Etapa 7: marca el lote como procesado."""
    batch_id = contexto["batch_id"]
    tarea = "registrar_resultado"
    conexion = conectar_redshift()
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "update ops.lotes set estado = 'procesado', procesado_en = %s, error = null where batch_id = %s",
            (ahora(), batch_id),
        )
        conexion.commit()
        conteos = {}
        for tabla in ("marts.fct_sales", "marts.fct_reviews", "marts.fct_navigation_events", "quarantine.quarantine_mysql__orders"):
            cursor.execute(f"select count(*) from {tabla}")
            conteos[tabla] = cursor.fetchone()[0]
    finally:
        conexion.close()
    _registrar(batch_id, tarea, "Lote procesado. Conteos del modelo: %s", conteos)
    return conteos


def marcar_fallo(contexto_airflow):
    """on_failure_callback: guarda en ops.lotes la tarea que fallo y el error."""
    instancia = contexto_airflow["task_instance"]
    datos = instancia.xcom_pull(task_ids="validar_configuracion")
    if not datos:
        LOGGER.error("Fallo %s antes de crear el lote; no hay nada que marcar.", instancia.task_id)
        return
    batch_id = datos["batch_id"]
    mensaje = f"{instancia.task_id}: {contexto_airflow.get('exception')}"
    LOGGER.error("[lote=%s tarea=%s] FALLO: %s", batch_id, instancia.task_id, mensaje)
    try:
        conexion = conectar_redshift()
        try:
            marcar_error(conexion.cursor(), batch_id, mensaje)
            conexion.commit()
        finally:
            conexion.close()
    except Exception:  # el callback nunca debe esconder el fallo original
        LOGGER.exception("No pude guardar el error del lote %s en ops.lotes", batch_id)
