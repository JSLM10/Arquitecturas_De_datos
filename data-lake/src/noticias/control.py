"""Estado de cada corrida: un JSON por (run_id, fuente) en control/lotes/, que Athena lee como ops_lotes.

Estados de una fuente: completa (feed válido) o fallida (HTTP, XML o respuesta vacía).
Estado de la corrida (fuente "_corrida"): completa, parcial (alguna fuente falló) o fallida (todas).
La etapa es la marca de avance; "publicado" significa que Silver y Gold ya incorporaron la corrida.
"""

from datetime import datetime, timezone

from . import s3util

ETAPAS = ("bronze", "limpiado", "enriquecido", "silver", "gold", "publicado")
CORRIDA = "_corrida"


def ahora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clave(run_id, fuente):
    return f"control/lotes/{run_id}__{fuente}.json"


def leer(run_id, fuente):
    return s3util.leer_json(clave(run_id, fuente)) if s3util.existe(clave(run_id, fuente)) else {}


def guardar(run_id, fuente, **campos):
    estado = leer(run_id, fuente)
    estado.update({"run_id": run_id, "fuente": fuente, **campos, "actualizado_utc": ahora_iso()})
    s3util.escribir_json(clave(run_id, fuente), estado, una_linea=True)  # Athena lee un objeto JSON por línea
    return estado


def corrida_publicada(run_id):
    return leer(run_id, CORRIDA).get("etapa") == "publicado"
