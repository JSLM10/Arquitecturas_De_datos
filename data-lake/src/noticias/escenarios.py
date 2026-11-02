"""Copias controladas de un RSS guardado en Bronze, para demostrar los escenarios sin depender de que
El Tiempo publique o edite noticias en ese momento.

Cada copia se guarda en Bronze como una corrida nueva, marcada con origen="copia_controlada" y con la
corrida de la que salió. Después se procesa con el pipeline normal (reprocesar_run=<id>).
"""

import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from lxml import etree

from . import bronze, control, rss, s3util, tablas

TEXTOS = [
    ("Gustavo Petro y Ecopetrol anuncian un acuerdo para exploración en Bogotá",
     "El presidente Gustavo Petro se reunió con directivos de Ecopetrol en Bogotá para revisar los contratos de gas."),
    ("Bancolombia y el Banco de la República ajustan proyecciones en Medellín",
     "Analistas de Bancolombia y del Banco de la República presentaron en Medellín nuevas cifras de inflación."),
    ("La Selección Colombia visitará Barranquilla antes de las eliminatorias",
     "El técnico Néstor Lorenzo confirmó que la Selección Colombia entrenará en Barranquilla con James Rodríguez."),
]


def _base(fuente, run_base=None):
    candidatas = [run_base] if run_base else reversed(bronze.corridas())
    for run in candidatas:
        presente = bronze.de_corrida(run).get(fuente)
        if presente and presente[0]["estado"] == "completa" and presente[0].get("origen") == "feed_real":
            return run, presente[0], presente[1]
    raise RuntimeError(f"No hay una corrida real de {fuente} en Bronze: corra primero la carga inicial")


def _item(guid, titulo, descripcion, momento, enlace=None):
    item = etree.Element("item")
    for etiqueta, valor in (("title", titulo), ("link", enlace if enlace is not None else f"https://www.eltiempo.com/controlado/{guid}"),
                            ("guid", guid), ("description", descripcion), ("pubDate", format_datetime(momento))):
        if valor is not None:
            etree.SubElement(item, etiqueta).text = valor
    return item


def _guardar(meta_base, run_base, raiz, tipo):
    usados = set(bronze.corridas())
    nuevo = bronze.nuevo_run_id()
    while nuevo in usados:
        time.sleep(1)
        nuevo = bronze.nuevo_run_id()
    ahora = datetime.now(timezone.utc)
    contenido = etree.tostring(raiz, encoding="utf-8", xml_declaration=True)
    ruta = bronze.prefijo(meta_base["fuente"], ahora.strftime("%Y-%m-%d"), nuevo)
    meta = {**meta_base, "run_id": nuevo, "ingestion_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bronze_key": ruta + "feed.xml", "bytes": len(contenido), "items_en_feed": len(list(raiz.iter("item"))),
            "origen": "copia_controlada", "copia_tipo": tipo, "copiado_de": run_base}
    s3util.poner(meta["bronze_key"], contenido, "application/xml")
    s3util.escribir_json(ruta + "_meta.json", meta)
    control.guardar(nuevo, meta["fuente"], url=meta["url"], ingesta_utc=meta["ingestion_utc"], http_status=200,
                    estado="completa", items_recibidos=meta["items_en_feed"], etapa="bronze", bronze_key=meta["bronze_key"])
    return nuevo


def modificada(fuente="economia", run_base=None):
    """Misma noticia con otro título y otra descripción: debe actualizarse y volver a pasar por Comprehend."""
    run, meta, xml = _base(fuente, run_base)
    raiz = rss.parsear_xml(xml)
    primero = next(raiz.iter("item"))
    primero.find("title").text = primero.find("title").text + " (versión corregida)"
    descripcion = primero.find("description")
    descripcion.text = "La redacción corrigió esta información tras nuevas declaraciones de Ecopetrol en Bogotá."
    return _guardar(meta, run, raiz, "modificada")


def nuevas(fuente="colombia", cantidad=3, run_base=None):
    """El feed original más noticias nuevas: solo esas deben incorporarse y enriquecerse."""
    run, meta, xml = _base(fuente, run_base)
    raiz = rss.parsear_xml(xml)
    canal = raiz.find("channel")
    ahora = datetime.now(timezone.utc)
    marca = ahora.strftime("%Y%m%d%H%M%S")
    for i in range(cantidad):
        titulo, descripcion = TEXTOS[i % len(TEXTOS)]
        canal.insert(list(canal).index(next(raiz.iter("item"))),
                     _item(f"controlado-{marca}-{i}", titulo, descripcion, ahora - timedelta(minutes=i)))
    return _guardar(meta, run, raiz, "nuevas")


def defectuosa(fuente="colombia", run_base=None):
    """El feed original más cuatro noticias con defectos y una repetida: las cuatro van a cuarentena."""
    run, meta, xml = _base(fuente, run_base)
    raiz = rss.parsear_xml(xml)
    canal = raiz.find("channel")
    ahora = datetime.now(timezone.utc)
    primera = next(raiz.iter("item"))
    sin_identificador = _item(None, "Noticia sin identificador", "No trae guid ni enlace.", ahora)
    sin_identificador.remove(sin_identificador.find("link"))
    fecha_ilegible = _item("defecto-fecha", "Noticia con fecha ilegible", "La fecha no se puede interpretar.", ahora)
    fecha_ilegible.find("pubDate").text = "ayer por la tarde"
    defectos = [
        _item("defecto-sin-titulo", "", "Noticia sin título.", ahora),
        fecha_ilegible,
        _item("defecto-enlace", "Noticia con enlace roto", "El enlace no es una URL.", ahora, enlace="esto-no-es-un-enlace"),
        sin_identificador,
    ]
    for defecto in defectos:
        canal.insert(list(canal).index(primera), defecto)
    canal.insert(list(canal).index(primera), etree.fromstring(etree.tostring(primera)))
    return _guardar(meta, run, raiz, "defectuosa")


def nueva_particion(fuente="deportes", run_base=None):
    """Noticias con una fecha de publicación que todavía no tiene partición en Silver."""
    run, meta, xml = _base(fuente, run_base)
    existentes = tablas.particiones_en_s3("silver_news")
    dia = datetime.now(timezone.utc) - timedelta(days=10)
    while dia.strftime("%Y-%m-%d") in existentes:
        dia -= timedelta(days=1)
    raiz = rss.parsear_xml(xml)
    canal = raiz.find("channel")
    marca = dia.strftime("%Y%m%d")
    for i in range(2):
        titulo, descripcion = TEXTOS[(i + 2) % len(TEXTOS)]
        canal.insert(list(canal).index(next(raiz.iter("item"))),
                     _item(f"controlado-particion-{marca}-{i}", titulo, descripcion, dia - timedelta(minutes=i)))
    return _guardar(meta, run, raiz, "nueva_particion")


COPIAS = {"modificada": modificada, "nuevas": nuevas, "defectuosa": defectuosa, "particion": nueva_particion}
