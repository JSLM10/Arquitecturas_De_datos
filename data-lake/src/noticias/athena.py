"""Consultas en Athena y validaciones finales del pipeline."""

import logging
import time

import boto3

from . import config

LOGGER = logging.getLogger(__name__)


def _athena():
    return boto3.client("athena", region_name=config.REGION)


def ejecutar(sql):
    """Corre una consulta y devuelve columnas, filas y los bytes que escaneó."""
    cliente = _athena()
    consulta = cliente.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": config.base_datos()}, WorkGroup=config.workgroup()
    )["QueryExecutionId"]
    while True:
        info = cliente.get_query_execution(QueryExecutionId=consulta)["QueryExecution"]
        estado = info["Status"]["State"]
        if estado in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if estado != "SUCCEEDED":
        raise RuntimeError(f"Athena {estado}: {info['Status'].get('StateChangeReason')} | {sql[:120]}")

    filas, columnas = [], None
    for pagina in cliente.get_paginator("get_query_results").paginate(QueryExecutionId=consulta):
        for fila in pagina["ResultSet"]["Rows"]:
            valores = [c.get("VarCharValue") for c in fila["Data"]]
            if columnas is None:
                columnas = valores
            else:
                filas.append(valores)
    return {"columnas": columnas or [], "filas": filas, "bytes": info["Statistics"].get("DataScannedInBytes", 0)}


def escalar(sql):
    resultado = ejecutar(sql)
    return int(float(resultado["filas"][0][0] or 0)) if resultado["filas"] else 0


VALIDACIONES = [
    ("Unicidad del identificador de noticia en Silver",
     "SELECT count(*) - count(DISTINCT news_id) FROM silver_news"),
    ("Campos obligatorios presentes",
     "SELECT count(*) FROM silver_news WHERE news_id IS NULL OR titulo IS NULL OR trim(titulo) = '' "
     "OR enlace IS NULL OR publicado_utc IS NULL"),
    ("Fechas y enlaces válidos",
     "SELECT count(*) FROM silver_news WHERE enlace NOT LIKE 'http%' "
     "OR CAST(publicado_utc AS date) <> CAST(fecha AS date)"),
    ("Entidades sin noticia asociada",
     "SELECT count(*) FROM silver_news_entities e LEFT JOIN silver_news n "
     "ON n.news_id = e.news_id AND n.fecha = e.fecha WHERE n.news_id IS NULL"),
    ("Frases clave sin noticia asociada",
     "SELECT count(*) FROM silver_news_key_phrases f LEFT JOIN silver_news n "
     "ON n.news_id = f.news_id AND n.fecha = f.fecha WHERE n.news_id IS NULL"),
    ("Conciliación Silver contra Gold (noticias)",
     "SELECT (SELECT count(*) FROM silver_news) - (SELECT coalesce(sum(noticias), 0) FROM gold_noticias_por_dia)"),
]


def validar():
    """Corre las validaciones. Cada una debe devolver 0. Lanza error si alguna falla."""
    resultados = []
    for nombre, sql in VALIDACIONES:
        diferencia = escalar(sql)
        resultados.append({"validacion": nombre, "diferencia": diferencia, "ok": diferencia == 0})
        LOGGER.info("Validación %s: %s", "OK" if diferencia == 0 else "FALLA", nombre)
    fallas = [r["validacion"] for r in resultados if not r["ok"]]
    if fallas:
        raise AssertionError(f"Validaciones fallidas: {fallas}")
    return resultados


CONSULTAS = {
    "Noticias por fecha y sección": (
        "SELECT fecha, seccion, sum(noticias) AS noticias FROM gold_noticias_por_dia "
        "GROUP BY fecha, seccion ORDER BY fecha DESC, seccion LIMIT 15"),
    "Diez organizaciones en más noticias": (
        "SELECT entidad, sum(noticias) AS noticias FROM gold_entidades_top WHERE tipo = 'ORGANIZATION' "
        "GROUP BY entidad ORDER BY noticias DESC, entidad LIMIT 10"),
    "Presencia de una entidad entre días": (
        "SELECT fecha, entidad, tipo, noticias FROM gold_entidades_top WHERE entidad = "
        "(SELECT entidad FROM gold_entidades_top GROUP BY entidad ORDER BY sum(noticias) DESC, entidad LIMIT 1) "
        "ORDER BY fecha, tipo"),
    "Frases clave más frecuentes por sección": (
        "SELECT seccion, frase, noticias FROM (SELECT seccion, frase, sum(noticias) AS noticias, "
        "row_number() OVER (PARTITION BY seccion ORDER BY sum(noticias) DESC, frase) AS puesto "
        "FROM gold_frases_por_seccion GROUP BY seccion, frase) WHERE puesto <= 3 ORDER BY seccion, noticias DESC"),
    "Conciliación Gold contra Silver": (
        "SELECT (SELECT count(*) FROM silver_news) AS noticias_silver, "
        "(SELECT sum(noticias) FROM gold_noticias_por_dia) AS noticias_gold"),
}


def comparar_particion():
    """Bytes escaneados por la misma consulta con y sin filtro de partición."""
    fecha = ejecutar("SELECT max(fecha) FROM silver_news")["filas"][0][0]
    con = ejecutar(f"SELECT count(*), count(DISTINCT titulo) FROM silver_news WHERE fecha = '{fecha}'")
    sin = ejecutar("SELECT count(*), count(DISTINCT titulo) FROM silver_news")
    return {"fecha": fecha, "con_filtro_bytes": con["bytes"], "sin_filtro_bytes": sin["bytes"]}
