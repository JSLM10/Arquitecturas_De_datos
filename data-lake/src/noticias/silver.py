"""Capa Silver: limpieza, validación, deduplicación y detección de cambios.

Cada noticia se identifica por su guid (o el hash del enlace). Frente a lo que ya está en Silver:
nueva (no existía), repetida (mismo contenido), actualizada (mismo id, otro título o descripción)
o rechazada (cuarentena, con su motivo y la ruta del archivo de Bronze).
Una noticia que aparece en varios feeds se publica una sola vez, con la sección del primer feed.
"""

import pandas as pd

from . import bronze, config, rss, s3util, tablas
from .esquemas import ESQUEMAS


def _registro(item, cfg, meta):
    titulo = rss.limpiar_html(item["titulo"])
    descripcion = rss.limpiar_html(item["descripcion"])
    publicado = rss.a_utc(item["fecha"])
    news_id = rss.id_noticia(item["guid"], item["enlace"])

    motivo = None
    if news_id is None:
        motivo = "sin_identificador"
    elif not titulo:
        motivo = "titulo_vacio"
    elif not rss.enlace_valido(item["enlace"]):
        motivo = "enlace_invalido"
    elif publicado is None:
        motivo = "fecha_invalida"

    registro = {
        "news_id": news_id, "fuente": cfg["fuente"], "medio": cfg["medio"], "seccion": cfg["seccion"],
        "titulo": titulo, "descripcion": descripcion, "enlace": item["enlace"],
        "publicado_utc": publicado.isoformat() if publicado else None,
        "publicado_original": item["fecha"],
        "content_hash": rss.hash_contenido(titulo, descripcion),
        "fecha": publicado.strftime("%Y-%m-%d") if publicado else None,
        "ultima_ingesta_utc": meta["ingestion_utc"], "run_id": meta["run_id"], "bronze_key": meta["bronze_key"],
    }
    rechazo = {
        "run_id": meta["run_id"], "fuente": cfg["fuente"], "guid": item["guid"], "titulo": titulo,
        "enlace": item["enlace"], "motivo": motivo, "bronze_key": meta["bronze_key"],
        "ingestado_utc": meta["ingestion_utc"], "fecha_ingesta": meta["ingestion_utc"][:10],
    }
    return registro, motivo, rechazo


def clasificar(run_id, actual):
    """Compara las noticias de una corrida de Bronze con las que ya están en Silver."""
    contenido = bronze.de_corrida(run_id)
    existentes = {}
    if len(actual):
        for fila in actual[["news_id", "content_hash", "fecha", "primera_ingesta_utc"]].itertuples(index=False):
            existentes[fila.news_id] = fila

    vistos, nuevas, actualizadas, rechazadas, por_fuente = set(), [], [], [], {}
    for cfg in config.fuentes():
        meta, xml = contenido.get(cfg["fuente"], (None, None))
        if meta is None:
            continue
        cuenta = {"estado": meta["estado"], "items": 0, "nuevas": 0, "repetidas": 0, "actualizadas": 0, "rechazadas": 0}
        por_fuente[cfg["fuente"]] = cuenta
        if meta["estado"] != "completa":
            continue
        for item in rss.items_de(xml):
            cuenta["items"] += 1
            registro, motivo, rechazo = _registro(item, cfg, meta)
            if motivo:
                rechazadas.append(rechazo)
                cuenta["rechazadas"] += 1
                continue
            if registro["news_id"] in vistos:
                cuenta["repetidas"] += 1
                continue
            vistos.add(registro["news_id"])
            previo = existentes.get(registro["news_id"])
            if previo is None:
                registro["primera_ingesta_utc"] = meta["ingestion_utc"]
                nuevas.append(registro)
                cuenta["nuevas"] += 1
            elif previo.content_hash == registro["content_hash"]:
                cuenta["repetidas"] += 1
            else:
                registro["fecha_anterior"] = previo.fecha
                registro["primera_ingesta_utc"] = pd.Timestamp(previo.primera_ingesta_utc).isoformat()
                actualizadas.append(registro)
                cuenta["actualizadas"] += 1
    return {"run_id": run_id, "nuevas": nuevas, "actualizadas": actualizadas, "rechazadas": rechazadas,
            "por_fuente": por_fuente}


def publicar_cuarentena(run_id, rechazadas):
    """Un archivo por (fecha de ingesta, corrida); repetir la corrida pisa el mismo archivo."""
    fechas = {r["fecha_ingesta"] for r in rechazadas}
    for clave in s3util.listar(tablas.prefijo("silver_cuarentena")):
        if clave.endswith(f"run_id={run_id}.parquet"):
            s3util.borrar(clave)
    for fecha in sorted(fechas):
        filas = [r for r in rechazadas if r["fecha_ingesta"] == fecha]
        marco = pd.DataFrame(filas)
        marco["ingestado_utc"] = pd.to_datetime(marco["ingestado_utc"]).dt.tz_localize(None)
        clave = f"{tablas.prefijo('silver_cuarentena')}fecha_ingesta={fecha}/run_id={run_id}.parquet"
        s3util.escribir_parquet(clave, marco, ESQUEMAS["silver_cuarentena"])
    return fechas


def _marco_noticias(registros, enriquecimiento):
    filas = []
    for r in registros:
        e = enriquecimiento[r["news_id"]]
        filas.append({
            **{c: r.get(c) for c in ESQUEMAS["silver_news"].names if c in r},
            "texto_analizado": e["texto_analizado"], "texto_hash": e["texto_hash"], "idioma": e["idioma"],
            "estado_enriquecimiento": e["estado"], "analizado_utc": e["analizado_utc"], "fecha": r["fecha"],
        })
    marco = pd.DataFrame(filas)
    for columna in ("publicado_utc", "analizado_utc", "primera_ingesta_utc", "ultima_ingesta_utc"):
        marco[columna] = pd.to_datetime(marco[columna], format="ISO8601", utc=True).dt.tz_localize(None)
    return tablas.fechas_en_ns(marco)


def aplicar(noticias, entidades, frases, cambios, enriquecimiento):
    """Aplica nuevas y actualizadas sobre Silver en memoria. Devuelve las tablas y las fechas afectadas."""
    registros = cambios["nuevas"] + cambios["actualizadas"]
    ids = {r["news_id"] for r in registros}
    fechas = {r["fecha"] for r in registros} | {r["fecha_anterior"] for r in cambios["actualizadas"]}
    if not registros:
        return noticias, entidades, frases, fechas

    nuevas_noticias = _marco_noticias(registros, enriquecimiento)
    filas_ent, filas_fr = [], []
    for r in registros:
        e = enriquecimiento[r["news_id"]]
        filas_ent += [{"news_id": r["news_id"], "texto_hash": e["texto_hash"], "fecha": r["fecha"], **x} for x in e["entidades"]]
        filas_fr += [{"news_id": r["news_id"], "texto_hash": e["texto_hash"], "fecha": r["fecha"], **x} for x in e["frases"]]

    noticias = pd.concat([noticias[~noticias["news_id"].isin(ids)], nuevas_noticias], ignore_index=True)
    entidades = pd.concat(
        [entidades[~entidades["news_id"].isin(ids)], pd.DataFrame(filas_ent, columns=tablas.tabla_vacia("silver_news_entities").columns)],
        ignore_index=True,
    )
    frases = pd.concat(
        [frases[~frases["news_id"].isin(ids)], pd.DataFrame(filas_fr, columns=tablas.tabla_vacia("silver_news_key_phrases").columns)],
        ignore_index=True,
    )
    return noticias, entidades, frases, fechas
