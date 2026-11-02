# Base de Glue (el_periodico), tablas explicitas de Silver, Gold y control, y el workgroup de Athena.
# Las columnas deben coincidir con los esquemas de src/noticias/esquemas.py (el pipeline lo verifica).
# Las particiones nuevas las registra el pipeline con la API de Glue (tarea actualizar_glue).

locals {
  formatos = {
    parquet = {
      entrada = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
      salida  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
      serde   = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    json = {
      entrada = "org.apache.hadoop.mapred.TextInputFormat"
      salida  = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
      serde   = "org.openx.data.jsonserde.JsonSerDe"
    }
  }

  tablas = {
    silver_news = {
      ruta      = "silver/news"
      formato   = "parquet"
      particion = "fecha"
      columnas = [
        ["news_id", "string"], ["fuente", "string"], ["medio", "string"], ["seccion", "string"],
        ["titulo", "string"], ["descripcion", "string"], ["enlace", "string"],
        ["publicado_utc", "timestamp"], ["publicado_original", "string"], ["content_hash", "string"],
        ["texto_analizado", "string"], ["texto_hash", "string"], ["idioma", "string"],
        ["estado_enriquecimiento", "string"], ["analizado_utc", "timestamp"],
        ["primera_ingesta_utc", "timestamp"], ["ultima_ingesta_utc", "timestamp"],
        ["run_id", "string"], ["bronze_key", "string"],
      ]
    }
    silver_news_entities = {
      ruta      = "silver/news_entities"
      formato   = "parquet"
      particion = "fecha"
      columnas = [
        ["news_id", "string"], ["entidad", "string"], ["tipo", "string"],
        ["score", "double"], ["menciones", "int"], ["texto_hash", "string"],
      ]
    }
    silver_news_key_phrases = {
      ruta      = "silver/news_key_phrases"
      formato   = "parquet"
      particion = "fecha"
      columnas = [
        ["news_id", "string"], ["frase", "string"], ["score", "double"], ["texto_hash", "string"],
      ]
    }
    silver_cuarentena = {
      ruta      = "silver/cuarentena"
      formato   = "parquet"
      particion = "fecha_ingesta"
      columnas = [
        ["run_id", "string"], ["fuente", "string"], ["guid", "string"], ["titulo", "string"],
        ["enlace", "string"], ["motivo", "string"], ["bronze_key", "string"], ["ingestado_utc", "timestamp"],
      ]
    }
    gold_noticias_por_dia = {
      ruta      = "gold/noticias_por_dia"
      formato   = "parquet"
      particion = "fecha"
      columnas  = [["medio", "string"], ["seccion", "string"], ["noticias", "bigint"]]
    }
    gold_entidades_top = {
      ruta      = "gold/entidades_top"
      formato   = "parquet"
      particion = "fecha"
      columnas  = [["tipo", "string"], ["entidad", "string"], ["noticias", "bigint"]]
    }
    gold_frases_por_seccion = {
      ruta      = "gold/frases_por_seccion"
      formato   = "parquet"
      particion = "fecha"
      columnas  = [["seccion", "string"], ["frase", "string"], ["noticias", "bigint"]]
    }
    ops_lotes = {
      ruta      = "control/lotes"
      formato   = "json"
      particion = ""
      columnas = [
        ["run_id", "string"], ["fuente", "string"], ["url", "string"], ["ingesta_utc", "string"],
        ["http_status", "int"], ["estado", "string"], ["items_recibidos", "int"],
        ["nuevas", "int"], ["repetidas", "int"], ["actualizadas", "int"], ["rechazadas", "int"],
        ["noticias_unicas_publicadas", "int"], ["etapa", "string"], ["error", "string"],
        ["bronze_key", "string"], ["actualizado_utc", "string"],
      ]
    }
  }
}

resource "aws_glue_catalog_database" "periodico" {
  name        = "el_periodico"
  description = "Noticias de El Tiempo: Silver, Gold y control del pipeline"
}

resource "aws_glue_catalog_table" "tabla" {
  for_each = local.tablas

  name          = each.key
  database_name = aws_glue_catalog_database.periodico.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    EXTERNAL       = "TRUE"
    classification = each.value.formato
  }

  dynamic "partition_keys" {
    for_each = each.value.particion == "" ? [] : [each.value.particion]

    content {
      name = partition_keys.value
      type = "string"
    }
  }

  storage_descriptor {
    location      = "s3://${var.bucket}/${each.value.ruta}/"
    input_format  = local.formatos[each.value.formato].entrada
    output_format = local.formatos[each.value.formato].salida

    ser_de_info {
      serialization_library = local.formatos[each.value.formato].serde
      parameters            = each.value.formato == "json" ? { "ignore.malformed.json" = "true" } : {}
    }

    dynamic "columns" {
      for_each = each.value.columnas

      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_athena_workgroup" "pregunton" {
  name          = "el-pregunton-lago"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration = true
    bytes_scanned_cutoff_per_query  = 10485760

    result_configuration {
      output_location = "s3://${var.bucket}/athena-resultados/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
