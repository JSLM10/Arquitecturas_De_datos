"""Herramientas de línea de comandos para los escenarios y la evidencia.

    python -m noticias.cli sql "<consulta>" | arbol | consultas | bytes | resumen | lotes | particiones | athena-cuenta
    python -m noticias.cli copia modificada|nuevas|defectuosa|particion [--fuente F] [--base RUN]
    python -m noticias.cli ultima [publicada|fallida]
"""

import argparse
import sys

from . import athena, bronze, control, escenarios, glue, s3util, tablas
from .esquemas import ESQUEMAS


def _tabla(columnas, filas):
    filas = [["" if v is None else str(v) for v in fila] for fila in filas]
    anchos = [max([len(c)] + [len(f[i]) for f in filas]) for i, c in enumerate(columnas)]
    print(" | ".join(c.ljust(anchos[i]) for i, c in enumerate(columnas)))
    print("-+-".join("-" * a for a in anchos))
    for fila in filas:
        print(" | ".join(v.ljust(anchos[i]) for i, v in enumerate(fila)))
    print(f"({len(filas)} filas)")


def arbol():
    for capa in ("bronze", "silver", "gold"):
        claves = [k for k in s3util.listar(capa + "/") if not k.endswith("/")]
        print(f"\n{capa}/  ({len(claves)} archivos)")
        for clave in claves[:12]:
            print("  " + clave)
        if len(claves) > 12:
            print(f"  ... y {len(claves) - 12} más")


def consultas():
    for titulo, sql in athena.CONSULTAS.items():
        resultado = athena.ejecutar(sql)
        print(f"\n== {titulo}")
        _tabla(resultado["columnas"], resultado["filas"])


def comparar_bytes():
    r = athena.comparar_particion()
    print(f"Partición elegida: fecha = {r['fecha']}")
    print(f"Con filtro de partición: {r['con_filtro_bytes']:>8} bytes escaneados")
    print(f"Sin filtro de partición: {r['sin_filtro_bytes']:>8} bytes escaneados")


def resumen():
    noticias = tablas.leer_tabla("silver_news")
    entidades = tablas.leer_tabla("silver_news_entities")
    frases = tablas.leer_tabla("silver_news_key_phrases")
    cuarentena = tablas.leer_tabla("silver_cuarentena")
    print(f"corridas en Bronze      : {len(bronze.corridas())}")
    print(f"noticias en Silver      : {noticias['news_id'].nunique()}")
    print(f"entidades en Silver     : {len(entidades)}")
    print(f"frases clave en Silver  : {len(frases)}")
    print(f"rechazadas (cuarentena) : {len(cuarentena)}")
    print(f"particiones de Silver   : {len(tablas.particiones_en_s3('silver_news'))}")


def lotes():
    resultado = athena.ejecutar(
        "SELECT run_id, fuente, estado, etapa, items_recibidos AS recibidos, nuevas, repetidas, actualizadas, "
        "rechazadas, noticias_unicas_publicadas AS unicas, substr(coalesce(error, ''), 1, 40) AS error "
        "FROM ops_lotes ORDER BY run_id DESC, fuente LIMIT 24"
    )
    _tabla(resultado["columnas"], resultado["filas"])


def athena_cuenta():
    en_athena = athena.escalar("SELECT count(*) FROM silver_news")
    en_s3 = int(tablas.leer_tabla("silver_news")["news_id"].nunique())
    en_glue = sum(len(glue.particiones_registradas(glue._glue(), t)) for t in ("silver_news",))
    print(f"Athena ve {en_athena} noticias; los archivos de S3 tienen {en_s3}; Glue tiene {en_glue} particiones de Silver")


def ultima(tipo):
    ids = sorted({k.split("__")[0].rsplit("/", 1)[-1] for k in s3util.listar("control/lotes/") if k.endswith(f"__{control.CORRIDA}.json")})
    for run in reversed(ids):
        estado = control.leer(run, control.CORRIDA)
        publicada = estado.get("etapa") == "publicado"
        if tipo == "publicada" and publicada and "+" not in run:
            return run
        if tipo == "fallida" and not publicada and estado.get("error"):
            return run
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("comando")
    parser.add_argument("argumento", nargs="?")
    parser.add_argument("--fuente")
    parser.add_argument("--base")
    args = parser.parse_args()

    simples = {"arbol": arbol, "consultas": consultas, "bytes": comparar_bytes, "resumen": resumen,
               "lotes": lotes, "athena-cuenta": athena_cuenta}
    if args.comando in simples:
        simples[args.comando]()
    elif args.comando == "sql":
        resultado = athena.ejecutar(args.argumento)
        _tabla(resultado["columnas"], resultado["filas"])
    elif args.comando == "particiones":
        print(glue.sincronizar())
    elif args.comando == "copia":
        if args.argumento not in escenarios.COPIAS:
            sys.exit(f"Tipos de copia: {', '.join(escenarios.COPIAS)}")
        parametros = {"run_base": args.base}
        if args.fuente:
            parametros["fuente"] = args.fuente
        print(escenarios.COPIAS[args.argumento](**parametros))
    elif args.comando == "ultima":
        print(ultima(args.argumento or "publicada") or "")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
