"""Lectura de claves desde AWS Secrets Manager. La clave vive en memoria; nunca se escribe ni se imprime."""

import json
from functools import lru_cache

import boto3

from .config import REGION


@lru_cache(maxsize=None)
def leer(arn):
    cliente = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(cliente.get_secret_value(SecretId=arn)["SecretString"])
