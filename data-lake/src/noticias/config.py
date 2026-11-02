"""Configuración del pipeline de noticias. Todo viene de variables de entorno; no hay secretos."""

import json
import os
from pathlib import Path

REGION = os.getenv("AWS_REGION", "us-east-2")
IDIOMAS_SOPORTADOS = {"es", "en"}
MAX_BYTES_TEXTO = 5000
TIPOS_ENTIDAD = ("PERSON", "ORGANIZATION", "LOCATION")


def requerida(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


def bucket():
    return requerida("DL_BUCKET")


def base_datos():
    return os.getenv("DL_BASE_DATOS", "el_periodico")


def workgroup():
    return os.getenv("DL_WORKGROUP", "el-pregunton-lago")


def fuentes():
    ruta = Path(__file__).with_name("fuentes.json")
    return json.loads(ruta.read_text(encoding="utf-8"))


def fuente(nombre):
    return next(f for f in fuentes() if f["fuente"] == nombre)
