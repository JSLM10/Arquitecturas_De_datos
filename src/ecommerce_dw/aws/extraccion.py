"""Extraccion de RDS y DocumentDB a S3, por lote.

Cada entidad deja en s3://<bucket>/raw/<fuente>/<entidad>/batch_id=<id>/ el CSV comprimido (gzip)
y un _manifest.json con fuente, lote, fecha, filas y marca de avance. Un lote nunca pisa a otro:
si el archivo ya existe, la extraccion se detiene.
"""

import csv
import gzip
import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone

import boto3
from botocore.exceptions import ClientError
from pymongo import MongoClient

from ecommerce_dw.ingestion.raw_sources import BATCH_SIZE, connect_mysql, flatten_mongo

from .config import REGION, requerida
from .entidades import ENTIDADES, clave_de, etiqueta_fuente

LOGGER = logging.getLogger(__name__)
MANIFIESTO = "_manifest.json"


def prefijo_s3(batch_id, nombre):
    definicion = ENTIDADES[nombre]
    return f"raw/{definicion['fuente']}/{definicion['origen']}/batch_id={batch_id}/"


def clave_datos(batch_id, nombre):
    return prefijo_s3(batch_id, nombre) + f"{ENTIDADES[nombre]['origen']}.csv.gz"


def _s3():
    return boto3.client("s3", region_name=REGION)


def _existe(s3, bucket, clave):
    try:
        s3.head_object(Bucket=bucket, Key=clave)
        return True
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def leer_manifiesto(batch_id, nombre):
    clave = prefijo_s3(batch_id, nombre) + MANIFIESTO
    try:
        objeto = _s3().get_object(Bucket=requerida("DW_BUCKET"), Key=clave)
    except ClientError as error:
        raise FileNotFoundError(f"No existe el lote {batch_id} de {nombre} en S3 ({clave})") from error
    return json.loads(objeto["Body"].read())


def _valor(valor):
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ")
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def _filas_mysql(nombre, marca):
    definicion = ENTIDADES[nombre]
    columnas = ", ".join(columna for columna, _ in definicion["columnas"])
    clave = clave_de(nombre)
    consulta = f"SELECT {columnas} FROM {definicion['origen']}"
    parametros = ()
    if marca is not None:
        consulta += f" WHERE {clave} > %s"
        parametros = (marca,)
    consulta += f" ORDER BY {clave}"

    conexion = connect_mysql()
    cursor = conexion.cursor()
    try:
        cursor.execute(consulta, parametros)
        while lote := cursor.fetchmany(BATCH_SIZE):
            yield from lote
    finally:
        cursor.close()
        conexion.close()


def _filas_mongo(nombre, marca):
    definicion = ENTIDADES[nombre]
    clave = clave_de(nombre)
    filtro = {} if marca is None else {clave: {"$gt": marca}}
    cliente = MongoClient(os.environ["MONGODB_URI"], tz_aware=True)
    try:
        base = cliente[os.getenv("MONGO_DATABASE", "ecommerce")]
        for documento in base[definicion["origen"]].find(filtro).sort(clave, 1).batch_size(BATCH_SIZE):
            _, valores = flatten_mongo(definicion["origen"], documento, None)
            yield valores[:-2]  # sin _loaded_at ni _source: esos los pone el extractor
    finally:
        cliente.close()


def extraer_entidad(nombre, batch_id, modo, marca_previa):
    """Extrae una entidad a S3 y devuelve su manifiesto. En modo incremental solo trae filas con clave mayor a marca_previa."""
    definicion = ENTIDADES[nombre]
    incremental = definicion["estrategia"] == "incremental" and modo == "incremental" and marca_previa is not None
    marca_inferior = marca_previa if incremental else None
    modo_real = "foto" if definicion["estrategia"] == "foto" else ("incremental" if incremental else "completo")

    bucket = requerida("DW_BUCKET")
    s3 = _s3()
    clave = clave_datos(batch_id, nombre)
    if _existe(s3, bucket, clave):
        raise FileExistsError(
            f"El lote {batch_id} ya existe en S3 ({clave}). Para repetirlo use reprocesar_lote={batch_id}; "
            "para traer datos nuevos deje que Airflow cree un batch_id nuevo."
        )

    filas = _filas_mysql(nombre, marca_inferior) if definicion["fuente"] == "mysql" else _filas_mongo(nombre, marca_inferior)
    cabecera = [columna for columna, _ in definicion["columnas"]] + ["_batch_id", "_source"]
    etiqueta = etiqueta_fuente(nombre)

    conteo, maxima = 0, marca_inferior
    temporal = tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False)
    temporal.close()
    try:
        with gzip.open(temporal.name, "wt", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(cabecera)
            for fila in filas:
                escritor.writerow([_valor(valor) for valor in fila] + [batch_id, etiqueta])
                conteo += 1
                if fila[0] is not None and (maxima is None or fila[0] > maxima):
                    maxima = fila[0]
        s3.upload_file(temporal.name, bucket, clave, ExtraArgs={"ServerSideEncryption": "AES256"})
    finally:
        os.unlink(temporal.name)

    manifiesto = {
        "batch_id": batch_id,
        "fuente": definicion["fuente"],
        "entidad": nombre,
        "modo": modo_real,
        "filas": conteo,
        "marca_inferior": marca_inferior,
        "marca_superior": maxima,
        "extraido_en_utc": datetime.now(timezone.utc).isoformat(),
        "bucket": bucket,
        "archivo": clave,
    }
    s3.put_object(
        Bucket=bucket,
        Key=prefijo_s3(batch_id, nombre) + MANIFIESTO,
        Body=json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )
    LOGGER.info("[lote=%s entidad=%s] %s filas (%s) -> s3://%s/%s", batch_id, nombre, conteo, modo_real, bucket, clave)
    return manifiesto
