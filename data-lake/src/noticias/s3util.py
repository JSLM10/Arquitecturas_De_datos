"""Acceso a S3 y lectura/escritura de Parquet."""

import io
import json
from functools import lru_cache

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

from .config import REGION, bucket


@lru_cache(maxsize=None)
def s3():
    return boto3.client("s3", region_name=REGION)


def existe(clave):
    try:
        s3().head_object(Bucket=bucket(), Key=clave)
        return True
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def poner(clave, datos, tipo="application/octet-stream"):
    s3().put_object(Bucket=bucket(), Key=clave, Body=datos, ContentType=tipo, ServerSideEncryption="AES256")


def leer(clave):
    return s3().get_object(Bucket=bucket(), Key=clave)["Body"].read()


def leer_json(clave):
    return json.loads(leer(clave))


def escribir_json(clave, objeto, una_linea=False):
    texto = json.dumps(objeto, ensure_ascii=False, indent=None if una_linea else 2)
    poner(clave, texto.encode("utf-8"), "application/json")


def listar(prefijo):
    claves = []
    for pagina in s3().get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefijo):
        claves.extend(objeto["Key"] for objeto in pagina.get("Contents", []))
    return claves


def borrar(clave):
    s3().delete_object(Bucket=bucket(), Key=clave)


def borrar_prefijo(prefijo):
    claves = listar(prefijo)
    for lote in range(0, len(claves), 1000):
        s3().delete_objects(
            Bucket=bucket(),
            Delete={"Objects": [{"Key": k} for k in claves[lote : lote + 1000]], "Quiet": True},
        )
    return len(claves)


def leer_parquet(clave):
    return pq.read_table(io.BytesIO(leer(clave))).to_pandas()


def escribir_parquet(clave, df, esquema):
    tabla = pa.Table.from_pandas(df[esquema.names], schema=esquema, preserve_index=False, safe=False)
    buffer = io.BytesIO()
    pq.write_table(tabla, buffer, compression="snappy", coerce_timestamps="ms", allow_truncated_timestamps=True)
    poner(clave, buffer.getvalue())
