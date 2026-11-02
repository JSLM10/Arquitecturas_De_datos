#!/usr/bin/env python3
"""Prueba de conexion a las bases del taller (RDS MySQL, DocumentDB y Redshift Serverless).

Se corre DESDE el compadre (la EC2), porque las bases solo dejan pasar a su portero.
Las claves se leen de Secrets Manager al momento de conectar: nunca se escriben ni se imprimen.

    python3 probar_conexiones.py rds      --endpoint <host> --secreto <arn>
    python3 probar_conexiones.py docdb    --endpoint <host> --secreto <arn> --cert global-bundle.pem
    python3 probar_conexiones.py redshift --workgroup <nombre> --secreto <arn> --base ecommerce_dw
"""
import argparse
import json
import sys
import time

import boto3

REGION = "us-east-2"


def leer_secreto(arn):
    """Trae usuario y clave del secreto. La clave se queda en memoria y no se imprime."""
    sm = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(sm.get_secret_value(SecretId=arn)["SecretString"])


def probar_rds(args):
    import pymysql

    cred = leer_secreto(args.secreto)
    con = pymysql.connect(
        host=args.endpoint,
        user=cred["username"],
        password=cred["password"],
        database=args.base,
        connect_timeout=10,
    )
    with con.cursor() as cur:
        cur.execute("SELECT VERSION(), CURRENT_USER(), DATABASE()")
        version, usuario, base = cur.fetchone()
    con.close()
    print(f"RDS MySQL  -> version={version} usuario={usuario} base={base}")


def probar_docdb(args):
    from pymongo import MongoClient

    cred = leer_secreto(args.secreto)
    cliente = MongoClient(
        host=args.endpoint,
        port=27017,
        username=cred["username"],
        password=cred["password"],
        tls=True,
        tlsCAFile=args.cert,
        retryWrites=False,  # DocumentDB no soporta retryable writes
        directConnection=True,
        serverSelectionTimeoutMS=10000,
    )
    cliente.admin.command("ping")
    version = cliente.server_info().get("version")
    print(f"DocumentDB -> ping ok, version={version}, bases={cliente.list_database_names()}")
    cliente.close()


def probar_redshift(args):
    data = boto3.client("redshift-data", region_name=REGION)
    ejecucion = data.execute_statement(
        WorkgroupName=args.workgroup,
        Database=args.base,
        SecretArn=args.secreto,
        Sql="SELECT current_database(), current_user, version()",
    )
    while True:
        estado = data.describe_statement(Id=ejecucion["Id"])
        if estado["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(2)
    if estado["Status"] != "FINISHED":
        sys.exit(f"Redshift -> {estado['Status']}: {estado.get('Error')}")
    fila = data.get_statement_result(Id=ejecucion["Id"])["Records"][0]
    base, usuario, version = (campo["stringValue"] for campo in fila)
    print(f"Redshift   -> base={base} usuario={usuario}\n              {version}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("servicio", choices=["rds", "docdb", "redshift"])
    parser.add_argument("--endpoint", help="host de RDS o DocumentDB")
    parser.add_argument("--secreto", required=True, help="ARN del secreto en Secrets Manager")
    parser.add_argument("--cert", default="global-bundle.pem", help="certificado TLS de DocumentDB")
    parser.add_argument("--workgroup", help="workgroup de Redshift Serverless")
    parser.add_argument("--base", default=None, help="nombre de la base de datos")
    args = parser.parse_args()

    if args.servicio == "rds":
        args.base = args.base or "ecommerce"
        probar_rds(args)
    elif args.servicio == "docdb":
        probar_docdb(args)
    else:
        args.base = args.base or "ecommerce_dw"
        probar_redshift(args)


if __name__ == "__main__":
    main()
