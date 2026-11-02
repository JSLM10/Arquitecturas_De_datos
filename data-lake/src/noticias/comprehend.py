"""Enriquecimiento con Amazon Comprehend: personas, organizaciones, lugares y frases clave.

Se analiza título + descripción. El resultado de cada texto se guarda en cache_comprehend/ con el hash del
texto: si el texto no cambió, no se vuelve a llamar al servicio. Los textos vacíos, de más de 5000 bytes o
en un idioma que Comprehend no cubre aquí quedan con un estado explícito y sin entidades ni frases.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

import boto3

from . import config, rss, s3util

LOGGER = logging.getLogger(__name__)
LOTE = 25


def _comprehend():
    return boto3.client("comprehend", region_name=config.REGION)


def texto_de(titulo, descripcion):
    return " ".join(p for p in (titulo, descripcion) if p).strip()


def _clave_cache(texto_hash):
    return f"cache_comprehend/texto_hash={texto_hash}.json"


def _ahora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entidades(lista):
    agrupadas = {}
    for e in lista:
        if e["Type"] not in config.TIPOS_ENTIDAD:
            continue
        texto = " ".join(e["Text"].split())
        clave = (texto.casefold(), e["Type"])
        previo = agrupadas.get(clave)
        if previo is None:
            agrupadas[clave] = {"entidad": texto, "tipo": e["Type"], "score": float(e["Score"]), "menciones": 1}
        else:
            previo["menciones"] += 1
            if e["Score"] > previo["score"]:
                previo.update(entidad=texto, score=float(e["Score"]))
    return list(agrupadas.values())


def _frases(lista):
    agrupadas = {}
    for f in lista:
        texto = " ".join(f["Text"].split())
        previo = agrupadas.get(texto.casefold())
        if previo is None or f["Score"] > previo["score"]:
            agrupadas[texto.casefold()] = {"frase": texto, "score": float(f["Score"])}
    return list(agrupadas.values())


def _lotes(elementos):
    for i in range(0, len(elementos), LOTE):
        yield elementos[i : i + LOTE]


def _llamar(cliente, metodo, textos, idioma):
    """Llama una API batch de Comprehend y devuelve {posicion: resultado}. Cualquier error del servicio falla."""
    salida = {}
    for inicio, lote in zip(range(0, len(textos), LOTE), _lotes(textos)):
        respuesta = getattr(cliente, metodo)(TextList=lote, LanguageCode=idioma) if idioma else getattr(cliente, metodo)(TextList=lote)
        if respuesta.get("ErrorList"):
            raise RuntimeError(f"Comprehend {metodo} devolvió errores: {respuesta['ErrorList']}")
        for elemento in respuesta["ResultList"]:
            salida[inicio + elemento["Index"]] = elemento
    return salida


def analizar(textos):
    """textos: {news_id: texto}. Devuelve ({news_id: resultado}, estadísticas)."""
    resultados, estadisticas = {}, defaultdict(int)
    pendientes = {}
    en_cache = {c for c in s3util.listar("cache_comprehend/")}

    for news_id, texto in textos.items():
        texto_hash = rss.hash_texto(texto)
        base = {"texto_analizado": texto, "texto_hash": texto_hash, "entidades": [], "frases": [], "idioma": None}
        if not texto:
            resultados[news_id] = {**base, "estado": "vacio", "analizado_utc": _ahora()}
        elif len(texto.encode("utf-8")) > config.MAX_BYTES_TEXTO:
            resultados[news_id] = {**base, "estado": "demasiado_largo", "analizado_utc": _ahora()}
        elif _clave_cache(texto_hash) in en_cache:
            guardado = s3util.leer_json(_clave_cache(texto_hash))
            resultados[news_id] = {**base, **{k: guardado[k] for k in ("estado", "idioma", "entidades", "frases", "analizado_utc")}}
            estadisticas["reutilizadas"] += 1
        else:
            pendientes[news_id] = base

    if pendientes:
        cliente = _comprehend()
        ids = list(pendientes)
        lista = [pendientes[i]["texto_analizado"] for i in ids]
        idiomas = _llamar(cliente, "batch_detect_dominant_language", lista, None)
        por_idioma = defaultdict(list)
        for posicion, news_id in enumerate(ids):
            candidatos = idiomas[posicion]["Languages"]
            codigo = max(candidatos, key=lambda x: x["Score"])["LanguageCode"] if candidatos else None
            pendientes[news_id]["idioma"] = codigo
            if codigo in config.IDIOMAS_SOPORTADOS:
                por_idioma[codigo].append(news_id)
            else:
                pendientes[news_id]["estado"] = "idioma_no_soportado"

        for codigo, grupo in por_idioma.items():
            textos_grupo = [pendientes[i]["texto_analizado"] for i in grupo]
            entidades = _llamar(cliente, "batch_detect_entities", textos_grupo, codigo)
            frases = _llamar(cliente, "batch_detect_key_phrases", textos_grupo, codigo)
            for posicion, news_id in enumerate(grupo):
                pendientes[news_id]["entidades"] = _entidades(entidades[posicion]["Entities"])
                pendientes[news_id]["frases"] = _frases(frases[posicion]["KeyPhrases"])
                pendientes[news_id]["estado"] = "completo"

        for news_id, resultado in pendientes.items():
            resultado["analizado_utc"] = _ahora()
            s3util.escribir_json(_clave_cache(resultado["texto_hash"]), {
                k: resultado[k] for k in ("texto_hash", "texto_analizado", "idioma", "estado", "entidades", "frases", "analizado_utc")
            })
            resultados[news_id] = resultado
            estadisticas["llamadas_nuevas"] += 1

    for resultado in resultados.values():
        estadisticas["estado_" + resultado["estado"]] += 1
    LOGGER.info("Comprehend: %s llamadas nuevas, %s reutilizadas desde la caché", estadisticas["llamadas_nuevas"],
                estadisticas["reutilizadas"])
    return resultados, dict(estadisticas)
