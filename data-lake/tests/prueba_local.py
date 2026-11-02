"""Prueba local de la lógica del pipeline, sin AWS: S3 simulado con moto y un Comprehend de mentira.

Requiere: pip install boto3 pandas pyarrow lxml "moto[s3]"
Uso (desde data-lake/src):  python ../tests/prueba_local.py <carpeta con colombia.xml economia.xml deportes.xml>
Athena y Glue no se simulan: se prueban en AWS.
"""

import os
import re
import sys
from pathlib import Path

os.environ.update(AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x", AWS_DEFAULT_REGION="us-east-2", AWS_REGION="us-east-2",
                  DL_BUCKET="lago-prueba")

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from noticias import bronze, comprehend, control, escenarios, gold, pipeline, s3util, silver, tablas  # noqa: E402

CARPETA = Path(sys.argv[1])
LLAMADAS = {"lotes": 0, "textos": 0}


class ComprehendFalso:
    def _res(self, textos, funcion):
        LLAMADAS["lotes"] += 1
        return {"ResultList": [{"Index": i, **funcion(t)} for i, t in enumerate(textos)], "ErrorList": []}

    def batch_detect_dominant_language(self, TextList):
        return self._res(TextList, lambda t: {"Languages": [{"LanguageCode": "es", "Score": 0.99}]})

    def batch_detect_entities(self, TextList, LanguageCode):
        LLAMADAS["textos"] += len(TextList)

        def entidades(texto):
            propios = re.findall(r"\b(?:[A-ZÁÉÍÓÚ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚ][a-záéíóúñ]+)*)\b", texto)
            tipos = ["PERSON", "ORGANIZATION", "LOCATION"]
            return {"Entities": [{"Text": p, "Type": tipos[i % 3], "Score": 0.9} for i, p in enumerate(propios)]}
        return self._res(TextList, entidades)

    def batch_detect_key_phrases(self, TextList, LanguageCode):
        return self._res(TextList, lambda t: {"KeyPhrases": [{"Text": " ".join(t.split()[:3]), "Score": 0.8}]})


def comprobar(condicion, mensaje):
    print(("  OK   " if condicion else "  FALLA ") + mensaje)
    if not condicion:
        raise SystemExit(1)


def ctx(run_id, **extra):
    base = {"run_id": run_id, "control_id": run_id, "reprocesar": False, "reconstruir": False,
            "simular_fallo": None, "registrar_glue": False, "fuente_caida": None}
    return {**base, **extra}


def correr(contexto):
    pipeline.limpiar_validar(contexto)
    pipeline.enriquecer(contexto)
    pipeline.publicar_silver(contexto)
    pipeline.construir_gold(contexto)
    pipeline.registrar_estado(contexto)


def noticias():
    return tablas.leer_tabla("silver_news")


with mock_aws():
    boto3.client("s3", region_name="us-east-2").create_bucket(
        Bucket="lago-prueba", CreateBucketConfiguration={"LocationConstraint": "us-east-2"})
    comprehend._comprehend = lambda: ComprehendFalso()

    print("\n1. Carga inicial")
    bronze.descargar = lambda url, **_: (200, (CARPETA / (url.rsplit("/", 1)[1])).read_bytes(), None)
    run1 = bronze.nuevo_run_id()
    for cfg in pipeline.config.fuentes():
        pipeline.extraer_fuente(cfg["fuente"], ctx(run1))
    correr(ctx(run1))
    base = noticias()
    comprobar(len(base) == 30, f"Silver tiene 30 noticias ({len(base)})")
    comprobar(base["news_id"].is_unique, "news_id es único")
    comprobar(len(tablas.leer_tabla("silver_news_entities")) > 0, "hay entidades")
    comprobar(control.corrida_publicada(run1), "la corrida quedó publicada")
    gold_noticias = tablas.leer_tabla("gold_noticias_por_dia")
    comprobar(int(gold_noticias["noticias"].sum()) == 30, "Gold concilia con Silver")
    textos_iniciales = LLAMADAS["textos"]

    print("\n2. Repetición de un lote exitoso")
    correr(ctx(run1, reprocesar=True, control_id=f"{run1}+reproceso-x"))
    comprobar(len(noticias()) == 30, "Silver sigue en 30")
    comprobar(LLAMADAS["textos"] == textos_iniciales, "Comprehend no se volvió a llamar")
    comprobar(control.leer(f"{run1}+reproceso-x", "colombia")["repetidas"] == 10, "las 10 de la fuente salen como repetidas")
    comprobar(control.leer(run1, "colombia")["nuevas"] == 10, "la corrida original conserva sus conteos")

    print("\n3. Nuevo lote incremental")
    run2 = escenarios.nuevas("colombia", 3)
    correr(ctx(run2, reprocesar=True))
    comprobar(len(noticias()) == 33, f"Silver pasó a 33 ({len(noticias())})")
    comprobar(LLAMADAS["textos"] == textos_iniciales + 3, "Comprehend analizó solo las 3 nuevas")
    previo = LLAMADAS["textos"]

    print("\n4. Registros defectuosos")
    run3 = escenarios.defectuosa("colombia")
    correr(ctx(run3, reprocesar=True))
    cuarentena = tablas.leer_tabla("silver_cuarentena")
    motivos = sorted(cuarentena["motivo"])
    comprobar(motivos == ["enlace_invalido", "fecha_invalida", "sin_identificador", "titulo_vacio"], f"cuarentena: {motivos}")
    comprobar(cuarentena["bronze_key"].str.startswith("bronze/").all(), "cada rechazo apunta a su archivo de Bronze")
    comprobar(len(noticias()) == 33, "Silver no cambió")
    comprobar(LLAMADAS["textos"] == previo, "sin llamadas nuevas a Comprehend")

    print("\n5. Noticia con contenido modificado")
    run4 = escenarios.modificada("economia")
    correr(ctx(run4, reprocesar=True))
    comprobar(len(noticias()) == 33, "sigue habiendo una fila por noticia")
    comprobar(noticias()["titulo"].str.contains("versión corregida").sum() == 1, "se actualizó el título vigente")
    comprobar(LLAMADAS["textos"] == previo + 1, "Comprehend analizó solo la noticia modificada")
    comprobar(control.leer(run4, "economia")["actualizadas"] == 1, "se registró 1 actualizada")

    print("\n6. Nueva partición")
    antes = tablas.particiones_en_s3("silver_news")
    run5 = escenarios.nueva_particion("deportes")
    correr(ctx(run5, reprocesar=True))
    despues = tablas.particiones_en_s3("silver_news")
    comprobar(len(despues) == len(antes) + 1, f"apareció 1 partición nueva ({sorted(despues - antes)})")

    print("\n7. Fallo controlado y recuperación")
    run6 = escenarios.nuevas("deportes", 2)
    total_antes = len(noticias())
    contexto = ctx(run6, reprocesar=True, simular_fallo="publicar_silver")
    pipeline.limpiar_validar(contexto)
    pipeline.enriquecer(contexto)
    try:
        pipeline.publicar_silver(contexto)
        comprobar(False, "debía fallar")
    except RuntimeError as error:
        comprobar("Fallo controlado" in str(error), "publicar_silver falló a propósito")
    comprobar(len(noticias()) == total_antes + 2, "quedaron noticias publicadas sin entidades (estado parcial)")
    comprobar(not control.corrida_publicada(run6), "la corrida no figura como publicada")
    llamadas_antes = LLAMADAS["textos"]
    correr(ctx(run6, reprocesar=True))
    comprobar(len(noticias()) == total_antes + 2 and noticias()["news_id"].is_unique, "recuperada sin duplicados")
    comprobar(LLAMADAS["textos"] == llamadas_antes, "la recuperación no repite llamadas a Comprehend")
    comprobar(control.corrida_publicada(run6), "la corrida quedó publicada")
    huerfanas = set(tablas.leer_tabla("silver_news_entities")["news_id"]) - set(noticias()["news_id"])
    comprobar(not huerfanas, "no hay entidades sin noticia")

    print("\n8. Reprocesamiento desde Bronze")
    antes = noticias().sort_values("news_id").reset_index(drop=True)[["news_id", "titulo", "content_hash", "fecha"]]
    entidades_antes = len(tablas.leer_tabla("silver_news_entities"))
    llamadas_antes = LLAMADAS["textos"]
    contexto = ctx(bronze.nuevo_run_id(), reconstruir=True)
    pipeline.limpiar_validar(contexto)
    pipeline.construir_gold(contexto)
    despues = noticias().sort_values("news_id").reset_index(drop=True)[["news_id", "titulo", "content_hash", "fecha"]]
    comprobar(antes.equals(despues), "Silver reconstruido idéntico al anterior")
    comprobar(len(tablas.leer_tabla("silver_news_entities")) == entidades_antes, "mismas entidades")
    comprobar(LLAMADAS["textos"] == llamadas_antes, "reconstruido sin llamar a Comprehend (caché)")

    print("\n9. Fuente caída")
    original = bronze.descargar
    bronze.descargar = lambda url, **_: (404, None, "HTTP 404") if "deportes" in url else original(url)
    run7 = bronze.nuevo_run_id()
    for cfg in pipeline.config.fuentes():
        pipeline.extraer_fuente(cfg["fuente"], ctx(run7))
    comprobar(control.leer(run7, "deportes")["estado"] == "fallida", "deportes quedó fallida (no 'sin noticias')")
    contexto = ctx(run7)
    pipeline.limpiar_validar(contexto)
    pipeline.enriquecer(contexto)
    pipeline.publicar_silver(contexto)
    pipeline.construir_gold(contexto)
    resultado = pipeline.registrar_estado(contexto)
    comprobar(resultado["estado"] == "parcial", "la corrida quedó parcial")

print("\nTodo bien.")
