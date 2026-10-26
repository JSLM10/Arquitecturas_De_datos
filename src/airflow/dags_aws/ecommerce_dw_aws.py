"""Pipeline del data warehouse en AWS: RDS y DocumentDB -> S3 -> Redshift -> dbt.

Etapas (todas con dependencias explicitas, sin intervencion manual entre una y otra):

  validar_configuracion
    -> extraer_mysql  \\
    -> extraer_mongo   -> cargar_a_redshift -> dbt_deps -> dbt_seed -> dbt_run_intermediate
    -> dbt_run_quarantine -> dbt_snapshot -> dbt_run_marts -> dbt_test -> registrar_resultado

Parametros al disparar (Trigger DAG w/ config):
  modo             auto (defecto), completo o incremental. auto = completo la primera vez e incremental despues.
  reprocesar_lote  batch_id de un lote que ya esta en S3. Rehace la carga y dbt SIN consultar las fuentes.

Si una tarea falla, el error queda en ops.lotes (columna error) junto con el batch_id y el nombre de la tarea.
"""

from datetime import datetime, timedelta, timezone

from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from airflow import DAG
from ecommerce_dw.aws.dbt_aws import correr_dbt
from ecommerce_dw.aws.pipeline import (
    cargar_lote,
    extraer_fuente,
    marcar_fallo,
    registrar_resultado,
    validar_configuracion,
)


def _validar(params, **_):
    return validar_configuracion(
        params.get("reprocesar_lote") or None,
        params.get("modo") or "auto",
        params.get("simular_fallo") or None,
    )


with DAG(
    dag_id="ecommerce_dw_aws",
    description="RDS MySQL y DocumentDB -> S3 -> Redshift -> dbt, por lotes",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    # Sin horario propio: se dispara a mano o con scripts/aws/compadre.sh pipeline.
    schedule=None,
    catchup=False,
    # Una sola corrida a la vez: evita escrituras que se pisen en raw y en los marts.
    max_active_runs=1,
    max_active_tasks=4,
    params={
        "modo": Param("auto", enum=["auto", "completo", "incremental"], description="Tipo de extraccion"),
        "reprocesar_lote": Param(None, type=["null", "string"], description="batch_id a reprocesar desde S3"),
        "simular_fallo": Param(
            None, type=["null", "string"], description="Solo para la demo: 'cargar_a_redshift' hace fallar la carga a proposito"
        ),
    },
    # Reintentos acotados (2) para fallos transitorios; al agotarlos se registra el error del lote.
    default_args={
        "retries": 2,
        "retry_delay": timedelta(seconds=30),
        "on_failure_callback": marcar_fallo,
    },
) as dag:
    validar = PythonOperator(task_id="validar_configuracion", python_callable=_validar)
    contexto = validar.output
    # Plantilla Jinja: Airflow la resuelve al ejecutar cada tarea con el batch_id que creo validar_configuracion.
    lote = "{{ ti.xcom_pull(task_ids='validar_configuracion')['batch_id'] }}"

    extraer_mysql = PythonOperator(
        task_id="extraer_mysql", python_callable=extraer_fuente, op_kwargs={"fuente": "mysql", "contexto": contexto}
    )
    extraer_mongo = PythonOperator(
        task_id="extraer_mongo", python_callable=extraer_fuente, op_kwargs={"fuente": "mongo", "contexto": contexto}
    )
    cargar = PythonOperator(task_id="cargar_a_redshift", python_callable=cargar_lote, op_kwargs={"contexto": contexto})

    def _dbt(task_id, comando, seleccion=None):
        return PythonOperator(
            task_id=task_id,
            python_callable=correr_dbt,
            op_kwargs={"comando": comando, "seleccion": seleccion, "lote": lote},
        )

    dbt_deps = _dbt("dbt_deps", "deps")
    dbt_seed = _dbt("dbt_seed", "seed")
    dbt_intermediate = _dbt("dbt_run_intermediate", "run", "path:models/intermediate")
    dbt_quarantine = _dbt("dbt_run_quarantine", "run", "path:models/quarantine")
    dbt_snapshot = _dbt("dbt_snapshot", "snapshot")
    dbt_marts = _dbt("dbt_run_marts", "run", "path:models/marts")
    dbt_test = _dbt("dbt_test", "test")
    resultado = PythonOperator(
        task_id="registrar_resultado", python_callable=registrar_resultado, op_kwargs={"contexto": contexto}
    )

    validar >> [extraer_mysql, extraer_mongo] >> cargar
    cargar >> dbt_deps >> dbt_seed >> dbt_intermediate >> dbt_quarantine >> dbt_snapshot >> dbt_marts >> dbt_test >> resultado
