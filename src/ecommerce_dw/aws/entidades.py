"""Las seis entidades del pipeline y como se extraen.

estrategia: foto (tabla completa en cada lote) o incremental (filas con clave mayor a la marca
del ultimo lote cargado). La clave es siempre la primera columna.
"""

ENTIDADES = {
    "customers": {
        "fuente": "mysql",
        "origen": "customers",
        "estrategia": "foto",
        "columnas": [
            ("customer_id", "BIGINT"), ("name", "VARCHAR(640)"), ("email", "VARCHAR(1016)"),
            ("phone", "VARCHAR(128)"), ("city", "VARCHAR(400)"), ("department", "VARCHAR(400)"),
            ("registration_date", "DATE"), ("updated_at", "TIMESTAMP"),
        ],
    },
    "products": {
        "fuente": "mysql",
        "origen": "products",
        "estrategia": "foto",
        "columnas": [
            ("product_id", "BIGINT"), ("name", "VARCHAR(720)"), ("category", "VARCHAR(320)"),
            ("price", "DECIMAL(12,2)"), ("description", "VARCHAR(2000)"), ("is_active", "BOOLEAN"),
            ("updated_at", "TIMESTAMP"),
        ],
    },
    "orders": {
        "fuente": "mysql",
        "origen": "orders",
        "estrategia": "incremental",
        "columnas": [
            ("order_id", "BIGINT"), ("customer_id", "BIGINT"), ("order_date", "TIMESTAMP"),
            ("status", "VARCHAR(80)"), ("sales_channel", "VARCHAR(120)"), ("payment_method", "VARCHAR(120)"),
            ("total", "DECIMAL(14,2)"),
        ],
    },
    "order_items": {
        "fuente": "mysql",
        "origen": "order_items",
        "estrategia": "incremental",
        "columnas": [
            ("order_item_id", "BIGINT"), ("order_id", "BIGINT"), ("product_id", "BIGINT"),
            ("quantity", "INTEGER"), ("unit_price", "DECIMAL(12,2)"), ("subtotal", "DECIMAL(14,2)"),
        ],
    },
    "reviews": {
        "fuente": "mongo",
        "origen": "reviews",
        "estrategia": "incremental",
        "columnas": [
            ("review_id", "BIGINT"), ("customer_id", "BIGINT"), ("product_id", "BIGINT"),
            ("rating", "INTEGER"), ("reviewed_at", "TIMESTAMPTZ"), ("document_json", "VARCHAR(65535)"),
        ],
    },
    "navigation_events": {
        "fuente": "mongo",
        "origen": "navigation_events",
        "estrategia": "incremental",
        "columnas": [
            ("event_id", "BIGINT"), ("event_type", "VARCHAR(200)"), ("occurred_at", "TIMESTAMPTZ"),
            ("customer_id", "BIGINT"), ("product_id", "BIGINT"), ("sales_channel", "VARCHAR(120)"),
            ("document_json", "VARCHAR(65535)"),
        ],
    },
}


def tabla_raw(nombre):
    definicion = ENTIDADES[nombre]
    return f"\"raw\".{definicion['fuente']}_{definicion['origen']}"


def etiqueta_fuente(nombre):
    definicion = ENTIDADES[nombre]
    prefijo = "mysql" if definicion["fuente"] == "mysql" else "mongodb"
    return f"{prefijo}.{definicion['origen']}"


def entidades_de(fuente):
    return [nombre for nombre, definicion in ENTIDADES.items() if definicion["fuente"] == fuente]


def clave_de(nombre):
    return ENTIDADES[nombre]["columnas"][0][0]
