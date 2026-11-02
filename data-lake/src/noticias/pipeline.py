"""Etapas del DAG de noticias. Cada función es una tarea y deja corrida, fuente y tarea en el log.

  1 validar_configuracion   2 extraer_fuente (Bronze)    3 limpiar_validar    4 enriquecer (Comprehend)
  5 publicar_silver         6 construir_gold             7 actualizar_glue    8 validar_athena
  9 registrar_estado

Entre tareas viaja solo el contexto (run_id y parámetros); los datos intermedios quedan en
stage/run_id=<id>/ del mismo bucket, así una tarea fallida se reanuda sin repetir lo anterior.
"""

import logging

import boto3

from . import athena, bronze, comprehend, config, control, glue, gold, rss, s3util, silver, tablas

LOGGER = logging.getLogger(__name__)
FALLOS = ("enriquecer", "publicar_silver")


def _log(run_id, tarea, mensaje, *args):
    LOGGER.info("[corrida=%s tarea=%s] " + mensaje, run_id, tarea, *args)


def _stage(run_id, nombre):
    return f"stage/run_id={run_id}/{nombre}.json"


def _marcar(run_id, cambios, etapa):
    for fuente, cuenta in cambios["por_fuente"].items():
        control.guardar(
            run_id, fuente, etapa=etapa, estado=cuenta["estado"], items_recibidos=cuenta["items"], nuevas=cuenta["nuevas"],
            repetidas=cuenta["repetidas"], actualizadas=cuenta["actualizadas"], rechazadas=cuenta["rechazadas"],
        )


def validar_configuracion(reprocesar_run=None, reconstruir=False, simular_fallo=None, registrar_glue=True,
                          fuente_caida=None):
    tarea = "validar_configuracion"
    if simular_fallo and simular_fallo not in FALLOS:
        raise ValueError(f"simular_fallo debe ser uno de {FALLOS}")
    for cfg in config.fuentes():
        if not rss.enlace_valido(cfg["url"]):
            raise ValueError(f"URL inválida en fuentes.json: {cfg}")

    run_id = reprocesar_run or bronze.nuevo_run_id()
    control_id = run_id
    boto3.client("s3", region_name=config.REGION).head_bucket(Bucket=config.bucket())
    boto3.client("glue", region_name=config.REGION).get_database(Name=config.base_datos())
    boto3.client("athena", region_name=config.REGION).get_work_group(WorkGroup=config.workgroup())
    boto3.client("comprehend", region_name=config.REGION).batch_detect_dominant_language(TextList=["validación"])
    _log(run_id, tarea, "S3, Glue, Athena y Comprehend responden")

    if reprocesar_run and not bronze.de_corrida(reprocesar_run):
        raise FileNotFoundError(f"La corrida {reprocesar_run} no existe en Bronze")
    if reprocesar_run:
        if control.corrida_publicada(run_id):
            control_id = f"{run_id}+reproceso-{bronze.nuevo_run_id()}"
        _log(run_id, tarea, "Se reprocesa desde Bronze: no se consultan los RSS")
    if reconstruir:
        _log(run_id, tarea, "Se reconstruyen Silver y Gold desde todo Bronze")
    return {"run_id": run_id, "control_id": control_id, "reprocesar": bool(reprocesar_run), "reconstruir": bool(reconstruir),
            "simular_fallo": simular_fallo, "registrar_glue": bool(registrar_glue), "fuente_caida": fuente_caida}


def extraer_fuente(fuente, ctx):
    run_id, tarea = ctx["run_id"], f"extraer_{fuente}"
    if ctx["reprocesar"] or ctx["reconstruir"]:
        _log(run_id, tarea, "Omitida: se trabaja desde Bronze")
        return {"omitida": True}
    cfg = dict(config.fuente(fuente))
    if ctx.get("fuente_caida") == fuente:
        cfg["url"] += "/no-existe"
        _log(run_id, tarea, "OJO: fuente caída simulada, se pide una URL inexistente")
    meta = bronze.extraer(cfg, run_id)
    return {"estado": meta["estado"], "items": meta["items_en_feed"], "error": meta["error"]}


def _reconstruir_silver(ctx):
    run_id, tarea = ctx["run_id"], "limpiar_validar"
    previas = {t: tablas.particiones_en_s3(t) for t in ("silver_news", "silver_news_entities", "silver_news_key_phrases")}
    noticias, entidades, frases = (tablas.tabla_vacia(t) for t in previas)
    llamadas = 0
    corridas = bronze.corridas()
    for corrida in corridas:
        cambios = silver.clasificar(corrida, noticias)
        silver.publicar_cuarentena(corrida, cambios["rechazadas"])
        registros = cambios["nuevas"] + cambios["actualizadas"]
        resultados, stats = comprehend.analizar({r["news_id"]: comprehend.texto_de(r["titulo"], r["descripcion"]) for r in registros})
        llamadas += stats.get("llamadas_nuevas", 0)
        noticias, entidades, frases, _ = silver.aplicar(noticias, entidades, frases, cambios, resultados)
    for tabla, marco in (("silver_news", noticias), ("silver_news_entities", entidades), ("silver_news_key_phrases", frases)):
        tablas.escribir_particiones(tabla, marco, set(marco["fecha"]) | previas[tabla])
    _log(run_id, tarea, "Reconstruido desde %s corridas de Bronze: %s noticias, %s llamadas nuevas a Comprehend",
         len(corridas), noticias["news_id"].nunique(), llamadas)
    return {"corridas": len(corridas), "noticias": int(noticias["news_id"].nunique()), "llamadas_nuevas": llamadas}


def limpiar_validar(ctx):
    run_id, tarea = ctx["run_id"], "limpiar_validar"
    if ctx["reconstruir"]:
        return _reconstruir_silver(ctx)

    clave = _stage(run_id, "clasificacion")
    if ctx["reprocesar"] and s3util.existe(clave) and not control.corrida_publicada(run_id):
        cambios = s3util.leer_json(clave)
        _log(run_id, tarea, "La corrida quedó a medias: se retoma la clasificación guardada")
    else:
        cambios = silver.clasificar(run_id, tablas.leer_tabla("silver_news"))
        if not any(c["estado"] == "completa" for c in cambios["por_fuente"].values()):
            raise RuntimeError("Ninguna fuente respondió bien: no hay nada que procesar")
        silver.publicar_cuarentena(run_id, cambios["rechazadas"])
        s3util.escribir_json(clave, cambios)
    _marcar(ctx["control_id"], cambios, "limpiado")
    resumen = {f: {k: v for k, v in c.items() if k != "estado"} for f, c in cambios["por_fuente"].items()}
    _log(run_id, tarea, "Clasificación por fuente: %s", resumen)
    return resumen


def enriquecer(ctx):
    run_id, tarea = ctx["run_id"], "enriquecer"
    if ctx["reconstruir"]:
        return {"omitida": True}
    if ctx["simular_fallo"] == "enriquecer":
        raise RuntimeError(f"Fallo controlado en enriquecer (corrida {run_id}): Silver y Gold no se tocaron")
    cambios = s3util.leer_json(_stage(run_id, "clasificacion"))
    registros = cambios["nuevas"] + cambios["actualizadas"]
    resultados, estadisticas = comprehend.analizar(
        {r["news_id"]: comprehend.texto_de(r["titulo"], r["descripcion"]) for r in registros}
    )
    s3util.escribir_json(_stage(run_id, "enriquecimiento"), resultados)
    _marcar(ctx["control_id"], cambios, "enriquecido")
    _log(run_id, tarea, "Textos analizados: %s", estadisticas)
    return estadisticas


def publicar_silver(ctx):
    run_id, tarea = ctx["run_id"], "publicar_silver"
    if ctx["reconstruir"]:
        return {"omitida": True}
    cambios = s3util.leer_json(_stage(run_id, "clasificacion"))
    resultados = s3util.leer_json(_stage(run_id, "enriquecimiento"))
    noticias, entidades, frases = (tablas.leer_tabla(t) for t in ("silver_news", "silver_news_entities", "silver_news_key_phrases"))
    noticias, entidades, frases, fechas = silver.aplicar(noticias, entidades, frases, cambios, resultados)

    tablas.escribir_particiones("silver_news", noticias, fechas)
    if ctx["simular_fallo"] == "publicar_silver":
        raise RuntimeError(f"Fallo controlado en publicar_silver (corrida {run_id}): quedaron noticias sin entidades")
    tablas.escribir_particiones("silver_news_entities", entidades, fechas)
    tablas.escribir_particiones("silver_news_key_phrases", frases, fechas)
    _marcar(ctx["control_id"], cambios, "silver")
    _log(run_id, tarea, "Particiones reescritas: %s", sorted(fechas))
    return {"particiones": sorted(fechas)}


def construir_gold(ctx):
    run_id, tarea = ctx["run_id"], "construir_gold"
    noticias, entidades, frases = (tablas.leer_tabla(t) for t in ("silver_news", "silver_news_entities", "silver_news_key_phrases"))
    escritas = gold.publicar(gold.construir(noticias, entidades, frases))
    _log(run_id, tarea, "Gold publicado: %s", escritas)
    return escritas


def actualizar_glue(ctx):
    run_id, tarea = ctx["run_id"], "actualizar_glue"
    if not ctx["registrar_glue"]:
        _log(run_id, tarea, "Omitida a propósito: las particiones nuevas no se registran")
        return {"omitida": True}
    return glue.sincronizar()


def validar_athena(ctx):
    run_id, tarea = ctx["run_id"], "validar_athena"
    resultados = athena.validar()
    _log(run_id, tarea, "%s validaciones correctas", len(resultados))
    return {"validaciones": len(resultados)}


def registrar_estado(ctx):
    run_id, tarea = ctx["run_id"], "registrar_estado"
    total = int(tablas.leer_tabla("silver_news")["news_id"].nunique())
    if ctx["reconstruir"]:
        control.guardar(ctx["control_id"], control.CORRIDA, estado="reconstruccion", etapa="publicado",
                        noticias_unicas_publicadas=total, error=None)
        _log(run_id, tarea, "Reconstrucción terminada: %s noticias únicas en Silver", total)
        return {"noticias_unicas": total}

    cambios = s3util.leer_json(_stage(run_id, "clasificacion"))
    _marcar(ctx["control_id"], cambios, "publicado")
    estados = [c["estado"] for c in cambios["por_fuente"].values()]
    if all(e == "completa" for e in estados):
        estado = "completa"
    elif any(e == "completa" for e in estados):
        estado = "parcial"
    else:
        estado = "fallida"
    totales = {k: sum(c[k] for c in cambios["por_fuente"].values()) for k in ("items", "nuevas", "repetidas", "actualizadas", "rechazadas")}
    control.guardar(ctx["control_id"], control.CORRIDA, estado=estado, etapa="publicado", items_recibidos=totales["items"],
                    nuevas=totales["nuevas"], repetidas=totales["repetidas"], actualizadas=totales["actualizadas"],
                    rechazadas=totales["rechazadas"], noticias_unicas_publicadas=total, error=None)
    _log(run_id, tarea, "Corrida %s: %s registros recibidos = %s nuevas + %s repetidas + %s actualizadas + %s rechazadas; "
         "noticias únicas publicadas en Silver: %s", estado, totales["items"], totales["nuevas"], totales["repetidas"],
         totales["actualizadas"], totales["rechazadas"], total)
    return {"estado": estado, **totales, "noticias_unicas": total}


def marcar_fallo(contexto):
    """on_failure_callback: guarda la tarea y el error en el estado de la corrida, sin cambiar su etapa."""
    instancia = contexto["task_instance"]
    ctx = instancia.xcom_pull(task_ids="validar_configuracion")
    if not ctx:
        LOGGER.error("Falló %s antes de crear la corrida", instancia.task_id)
        return
    mensaje = f"{instancia.task_id}: {contexto.get('exception')}"
    LOGGER.error("[corrida=%s tarea=%s] FALLO: %s", ctx["run_id"], instancia.task_id, mensaje)
    try:
        control.guardar(ctx["control_id"], control.CORRIDA, error=mensaje[:1000])
    except Exception:
        LOGGER.exception("No se pudo guardar el error de la corrida %s", ctx["run_id"])
