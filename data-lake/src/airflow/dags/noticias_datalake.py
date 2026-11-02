"""Pipeline del data lake de noticias (El Tiempo): RSS -> Bronze -> Silver -> Gold -> Glue -> Athena.

  validar_configuracion -> extraer_<fuente> (en paralelo) -> limpiar_validar -> enriquecer_comprehend
  -> publicar_silver -> construir_gold -> actualizar_glue -> validar_athena -> registrar_estado

Parámetros al disparar el DAG (Trigger DAG w/ config):
  reprocesar_run  corrida de Bronze a reprocesar, sin consultar los RSS
  reconstruir     borra Silver y Gold y los rehace desde todo Bronze
  registrar_glue  false omite el registro de particiones nuevas (solo para la demostración)
  simular_fallo   enriquecer | publicar_silver: la tarea falla a propósito
  fuente_caida    nombre de una fuente a la que se le pide una URL inexistente
"""

import os
from datetime import datetime, timedelta, timezone

from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from airflow import DAG
from noticias import config, pipeline


def _validar(params, **_):
    return pipeline.validar_configuracion(
        params.get("reprocesar_run") or None,
        bool(params.get("reconstruir")),
        params.get("simular_fallo") or None,
        bool(params.get("registrar_glue", True)),
        params.get("fuente_caida") or None,
    )


with DAG(
    dag_id="noticias_datalake",
    description="Noticias RSS de El Tiempo en un data lake medallón sobre S3",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    # Cada hora mientras dure el laboratorio (scripts/compadre.sh programar on); sin horario, solo manual.
    schedule="0 * * * *" if os.getenv("DL_PROGRAMAR") == "1" else None,
    catchup=False,
    # Una sola corrida a la vez: evita escrituras que se pisen en Silver y Gold.
    max_active_runs=1,
    params={
        "reprocesar_run": Param("", type="string"),
        "reconstruir": Param(False, type="boolean"),
        "registrar_glue": Param(True, type="boolean"),
        "simular_fallo": Param("", type="string", enum=["", "enriquecer", "publicar_silver"]),
        "fuente_caida": Param("", type="string"),
    },
    default_args={"retries": 2, "retry_delay": timedelta(seconds=30), "on_failure_callback": pipeline.marcar_fallo},
) as dag:
    validar = PythonOperator(task_id="validar_configuracion", python_callable=_validar)
    ctx = validar.output

    extracciones = [
        PythonOperator(task_id=f"extraer_{cfg['fuente']}", python_callable=pipeline.extraer_fuente,
                       op_kwargs={"fuente": cfg["fuente"], "ctx": ctx})
        for cfg in config.fuentes()
    ]

    def tarea(identificador, funcion):
        return PythonOperator(task_id=identificador, python_callable=funcion, op_kwargs={"ctx": ctx})

    limpiar = tarea("limpiar_validar", pipeline.limpiar_validar)
    enriquecer = tarea("enriquecer_comprehend", pipeline.enriquecer)
    silver = tarea("publicar_silver", pipeline.publicar_silver)
    gold = tarea("construir_gold", pipeline.construir_gold)
    glue = tarea("actualizar_glue", pipeline.actualizar_glue)
    athena = tarea("validar_athena", pipeline.validar_athena)
    registro = tarea("registrar_estado", pipeline.registrar_estado)

    validar >> extracciones >> limpiar >> enriquecer >> silver >> gold >> glue >> athena >> registro
