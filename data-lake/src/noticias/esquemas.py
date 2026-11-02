"""Esquemas de las tablas en Parquet. Deben coincidir con las tablas de Glue definidas en Terraform."""

import pyarrow as pa

TS = pa.timestamp("ms")
S, D, I, B = pa.string(), pa.float64(), pa.int32(), pa.int64()

ESQUEMAS = {
    "silver_news": pa.schema([
        ("news_id", S), ("fuente", S), ("medio", S), ("seccion", S), ("titulo", S), ("descripcion", S),
        ("enlace", S), ("publicado_utc", TS), ("publicado_original", S), ("content_hash", S),
        ("texto_analizado", S), ("texto_hash", S), ("idioma", S), ("estado_enriquecimiento", S),
        ("analizado_utc", TS), ("primera_ingesta_utc", TS), ("ultima_ingesta_utc", TS),
        ("run_id", S), ("bronze_key", S),
    ]),
    "silver_news_entities": pa.schema([
        ("news_id", S), ("entidad", S), ("tipo", S), ("score", D), ("menciones", I), ("texto_hash", S),
    ]),
    "silver_news_key_phrases": pa.schema([
        ("news_id", S), ("frase", S), ("score", D), ("texto_hash", S),
    ]),
    "silver_cuarentena": pa.schema([
        ("run_id", S), ("fuente", S), ("guid", S), ("titulo", S), ("enlace", S), ("motivo", S),
        ("bronze_key", S), ("ingestado_utc", TS),
    ]),
    "gold_noticias_por_dia": pa.schema([("medio", S), ("seccion", S), ("noticias", B)]),
    "gold_entidades_top": pa.schema([("tipo", S), ("entidad", S), ("noticias", B)]),
    "gold_frases_por_seccion": pa.schema([("seccion", S), ("frase", S), ("noticias", B)]),
}

RUTAS = {
    "silver_news": "silver/news",
    "silver_news_entities": "silver/news_entities",
    "silver_news_key_phrases": "silver/news_key_phrases",
    "silver_cuarentena": "silver/cuarentena",
    "gold_noticias_por_dia": "gold/noticias_por_dia",
    "gold_entidades_top": "gold/entidades_top",
    "gold_frases_por_seccion": "gold/frases_por_seccion",
}

PARTICIONES = {tabla: "fecha" for tabla in RUTAS}
PARTICIONES["silver_cuarentena"] = "fecha_ingesta"

TIPOS_GLUE = {"string": "string", "timestamp": "timestamp", "double": "double", "int": "int", "bigint": "bigint"}


def tipo_glue(tipo):
    if pa.types.is_string(tipo):
        return "string"
    if pa.types.is_timestamp(tipo):
        return "timestamp"
    if pa.types.is_float64(tipo):
        return "double"
    if pa.types.is_int32(tipo):
        return "int"
    return "bigint"
