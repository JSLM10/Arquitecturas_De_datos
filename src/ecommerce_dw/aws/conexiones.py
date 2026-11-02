"""Conexiones a RDS MySQL, DocumentDB y Redshift. Las claves se leen de Secrets Manager al conectar."""

import os
from urllib.parse import quote_plus

import redshift_connector

from .config import requerida
from .secretos import leer

RUTA_CERT_DOCDB = os.getenv("DOCDB_CERT", "/opt/airflow/certs/global-bundle.pem")


def preparar_entorno_fuentes():
    """Deja en el entorno las variables que usan los scripts de ecommerce_dw.sources, con las claves de Secrets Manager."""
    rds = leer(requerida("RDS_SECRET_ARN"))
    os.environ["MYSQL_HOST"] = requerida("RDS_ENDPOINT")
    os.environ["MYSQL_PORT"] = "3306"
    os.environ["MYSQL_USER"] = rds["username"]
    os.environ["MYSQL_PASSWORD"] = rds["password"]
    os.environ.setdefault("MYSQL_DATABASE", "ecommerce")

    docdb = leer(requerida("DOCDB_SECRET_ARN"))
    usuario, clave = quote_plus(docdb["username"]), quote_plus(docdb["password"])
    # DocumentDB: TLS obligatorio, sin retryWrites y conexion directa al nodo del cluster.
    os.environ["MONGODB_URI"] = (
        f"mongodb://{usuario}:{clave}@{requerida('DOCDB_ENDPOINT')}:27017/"
        f"?tls=true&tlsCAFile={RUTA_CERT_DOCDB}&retryWrites=false&directConnection=true"
    )
    os.environ.setdefault("MONGO_DATABASE", "ecommerce")
    # DocumentDB no soporta validadores $jsonSchema: los scripts de fuentes lo respetan con esta marca.
    os.environ["MONGO_SIN_VALIDADOR"] = "1"


def conectar_redshift():
    credenciales = leer(requerida("REDSHIFT_SECRET_ARN"))
    return redshift_connector.connect(
        host=requerida("REDSHIFT_ENDPOINT"),
        port=5439,
        database=requerida("REDSHIFT_DB"),
        user=credenciales["username"],
        password=credenciales["password"],
        timeout=30,
        ssl=True,
        sslmode="require",
    )
