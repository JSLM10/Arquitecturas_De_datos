"""Capa Bronze: el XML original de cada feed, tal como llegó, más un archivo de metadatos.

bronze/source=<fuente>/ingestion_date=AAAA-MM-DD/run_id=<id>/feed.xml
bronze/source=<fuente>/ingestion_date=AAAA-MM-DD/run_id=<id>/_meta.json

Solo se guardan respuestas válidas (HTTP 200, con contenido y XML bien formado). Una fuente caída
queda registrada como fallida: nunca se confunde con una fuente sin noticias.
"""

import hashlib
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from lxml import etree

from . import control, rss, s3util

LOGGER = logging.getLogger(__name__)
AGENTE = "Mozilla/5.0 (compatible; taller-datalake-eia)"


def nuevo_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def prefijo(fuente, fecha, run_id):
    return f"bronze/source={fuente}/ingestion_date={fecha}/run_id={run_id}/"


def descargar(url, intentos=3, espera=3):
    """Devuelve (estado_http, contenido, error). Reintenta ante fallos de red o respuestas 5xx."""
    ultimo = (None, None, "sin intentos")
    for intento in range(1, intentos + 1):
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(peticion, timeout=20) as respuesta:
                return respuesta.status, respuesta.read(), None
        except urllib.error.HTTPError as error:
            ultimo = (error.code, None, f"HTTP {error.code}")
            if error.code < 500:
                break
        except Exception as error:
            ultimo = (None, None, f"{type(error).__name__}: {error}")
        if intento < intentos:
            time.sleep(espera * intento)
    return ultimo


def validar_feed(contenido):
    """Devuelve (items, error). error es None si la respuesta sirve."""
    if not contenido or not contenido.strip():
        return 0, "respuesta vacía"
    try:
        return len(rss.items_de(contenido)), None
    except etree.XMLSyntaxError as error:
        return 0, f"XML malformado: {error}"


def extraer(cfg, run_id):
    """Descarga una fuente y deja en Bronze su contenido original y sus metadatos."""
    ahora = datetime.now(timezone.utc)
    ruta = prefijo(cfg["fuente"], ahora.strftime("%Y-%m-%d"), run_id)
    meta = {
        "run_id": run_id, "fuente": cfg["fuente"], "medio": cfg["medio"], "seccion": cfg["seccion"],
        "url": cfg["url"], "ingestion_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "http_status": None, "sha256": None, "bytes": 0, "bronze_key": None, "estado": "fallida",
        "items_en_feed": 0, "error": None, "origen": "feed_real",
    }
    if s3util.existe(ruta + "_meta.json"):
        raise FileExistsError(f"Bronze ya tiene {ruta}: un lote no se sobrescribe")

    estado, contenido, error = descargar(cfg["url"])
    meta["http_status"] = estado
    items = 0
    if error is None:
        items, error = validar_feed(contenido)
    if error is None:
        meta.update(
            estado="completa", items_en_feed=items, sha256=hashlib.sha256(contenido).hexdigest(),
            bytes=len(contenido), bronze_key=ruta + "feed.xml",
        )
        s3util.poner(meta["bronze_key"], contenido, "application/xml")
    else:
        meta["error"] = error
    s3util.escribir_json(ruta + "_meta.json", meta)

    control.guardar(
        run_id, cfg["fuente"], url=cfg["url"], ingesta_utc=meta["ingestion_utc"], http_status=estado,
        estado=meta["estado"], items_recibidos=items, etapa="bronze", error=meta["error"],
        bronze_key=meta["bronze_key"],
    )
    LOGGER.info("[corrida=%s fuente=%s] %s, %s noticias en el feed%s", run_id, cfg["fuente"], meta["estado"], items,
                f" ({error})" if error else "")
    return meta


def corridas():
    """run_id de todas las corridas con metadatos en Bronze, de la más antigua a la más reciente."""
    ids = set()
    for clave in s3util.listar("bronze/"):
        coincidencia = re.search(r"run_id=([^/]+)/_meta\.json$", clave)
        if coincidencia:
            ids.add(coincidencia.group(1))
    return sorted(ids)


def de_corrida(run_id):
    """Devuelve {fuente: (meta, contenido_xml o None)} de una corrida guardada en Bronze."""
    resultado = {}
    for clave in s3util.listar("bronze/"):
        if clave.endswith(f"run_id={run_id}/_meta.json"):
            meta = s3util.leer_json(clave)
            contenido = s3util.leer(meta["bronze_key"]) if meta.get("bronze_key") else None
            resultado[meta["fuente"]] = (meta, contenido)
    return resultado
