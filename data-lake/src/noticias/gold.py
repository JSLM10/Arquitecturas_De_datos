"""Capa Gold: indicadores agregados, siempre derivados de Silver.

Se cuentan noticias distintas (no menciones): una entidad repetida dentro de un mismo texto cuenta una vez.
Una noticia pertenece a una sola fecha (la de publicación en UTC), por lo que sumar entre fechas no cuenta dos veces.
Las noticias sin fecha de publicación válida no entran a Silver (van a cuarentena) y por eso tampoco a Gold.
"""

from . import tablas


def construir(noticias, entidades, frases):
    por_dia = (
        noticias.groupby(["fecha", "medio", "seccion"])["news_id"].nunique().reset_index(name="noticias")
    )

    validas = noticias[["news_id"]]
    ent = entidades.merge(validas, on="news_id")
    ent = ent.assign(clave=ent["entidad"].str.casefold())
    entidades_top = (
        ent.groupby(["fecha", "tipo", "clave"])
        .agg(entidad=("entidad", lambda s: s.mode().iat[0]), noticias=("news_id", "nunique"))
        .reset_index()
        .drop(columns="clave")
    ) if len(ent) else tablas.tabla_vacia("gold_entidades_top")

    fr = frases.merge(noticias[["news_id", "seccion"]], on="news_id")
    fr = fr.assign(clave=fr["frase"].str.casefold())
    frases_seccion = (
        fr.groupby(["fecha", "seccion", "clave"])
        .agg(frase=("frase", lambda s: s.mode().iat[0]), noticias=("news_id", "nunique"))
        .reset_index()
        .drop(columns="clave")
    ) if len(fr) else tablas.tabla_vacia("gold_frases_por_seccion")

    return {
        "gold_noticias_por_dia": por_dia if len(por_dia) else tablas.tabla_vacia("gold_noticias_por_dia"),
        "gold_entidades_top": entidades_top,
        "gold_frases_por_seccion": frases_seccion,
    }


def publicar(gold):
    """Reescribe todas las particiones de Gold y borra las que ya no tienen datos."""
    escritas = {}
    for tabla, marco in gold.items():
        fechas = set(marco["fecha"]) | tablas.particiones_en_s3(tabla)
        tablas.escribir_particiones(tabla, marco, fechas)
        escritas[tabla] = len(marco)
    return escritas
