"""Ejecuta dbt contra Redshift desde Airflow.
La clave sale de Secrets Manager y solo viaja en el entorno del proceso de dbt.
"""

import logging
import os
import subprocess

from .config import requerida
from .secretos import leer

DBT = "/home/airflow/dbt-venv/bin/dbt"
PROYECTO = "/opt/airflow/src/dbt_redshift"
LOGGER = logging.getLogger(__name__)


def correr_dbt(comando, seleccion=None, lote=None):
    argumentos = [DBT, "--no-use-colors", comando, "--project-dir", PROYECTO, "--profiles-dir", PROYECTO]
    if comando != "deps":
        argumentos += ["--target-path", "/tmp/dbt_target", "--log-path", "/tmp/dbt_logs"]
    if seleccion:
        argumentos += ["--select", seleccion]

    entorno = dict(os.environ)
    if comando != "deps":
        credenciales = leer(requerida("REDSHIFT_SECRET_ARN"))
        entorno.update(
            REDSHIFT_HOST=requerida("REDSHIFT_ENDPOINT"),
            REDSHIFT_DB=requerida("REDSHIFT_DB"),
            REDSHIFT_USER=credenciales["username"],
            REDSHIFT_PASSWORD=credenciales["password"],
        )
    LOGGER.info("[lote=%s tarea=dbt_%s] %s", lote, comando, " ".join(argumentos[1:]))
    # Cada linea de dbt pasa por el log de Airflow: asi el resultado (PASS, FAIL, ERROR) queda en la tarea.
    proceso = subprocess.Popen(argumentos, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for linea in proceso.stdout:
        LOGGER.info("[dbt] %s", linea.rstrip())
    if proceso.wait() != 0:
        raise RuntimeError(f"dbt {comando} termino con codigo {proceso.returncode} (lote {lote}); el detalle esta arriba en este log")
