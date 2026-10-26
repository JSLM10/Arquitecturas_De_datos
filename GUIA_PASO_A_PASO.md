# Guía paso a paso: Data Warehouse en AWS

Esta guía te lleva de la mano. Cada punto dice **qué comando correr**, **qué debes ver** y **a qué tomarle captura** (con el nombre del archivo que va en `evidencias/`).

> **Cuenta:** `112188880548` · **Región:** `us-east-2` (Ohio) · **Usuario:** `user_cli` · **Entorno:** WSL (Ubuntu)
> Puntos 0 a 5: infraestructura con Terraform. Puntos 6 a 9: el pipeline (Airflow, S3, Redshift, dbt, escenarios y QuickSight). Punto 10: borrar todo.

## Glosario costeño de los recursos

| Nombre | Recurso | Significado |
|---|---|---|
| `el-barrio-dw` | VPC | El barrio: la red donde vive todo |
| `la-esquina-a/b/c-dw` | Subredes | Donde se junta la gente |
| `la-puerta-al-mar-dw` | Internet Gateway | La salida al mar (Internet) |
| `la-calle-principal-dw` | Tabla de rutas | Por dónde se va a cada lado |
| `la-trocha-a-la-bodega-dw` | Endpoint de S3 | El atajo hasta la bodega |
| `la-bodega-del-pelao-dw-<cuenta>` | Bucket de S3 | Donde el pelao guarda sus cosas |
| `el-portero-*` | Grupos de seguridad | El portero decide quién entra |
| `el-compadre-dw` | EC2 (Airflow y dbt) | El compadre que acompaña y ayuda |
| `el-sancocho-dw` | RDS MySQL | Un poquito de todo en la misma olla |
| `el-bololo-dw` | DocumentDB | El revuelto: documentos sin forma fija |
| `la-picotera-dw` | Redshift Serverless | El sonido grande para mover mucha data |
| `la-picotera-lee-la-bodega` | Rol de IAM | Deja a la picotera leer la bodega |
| `el-compadre-airflow-rol` | Rol de IAM | Lo que el compadre puede hacer |

---

## Cómo entrar a WSL desde tu carpeta

1. Abre la carpeta `actividad-DataLake-DataWarehouse` en el Explorador de archivos.
2. Haz clic en la barra de direcciones, escribe `cmd` y pulsa Enter. Se abre el Símbolo del sistema en esa carpeta.
3. Escribe:

```bat
wsl -d Ubuntu-24.04
```

4. Verifica que estás en la carpeta correcta:

```bash
pwd && ls
```

Debe decir `/mnt/c/Users/juanp/Desktop/actividad-DataLake-DataWarehouse`. Si no, entra con:

```bash
cd /mnt/c/Users/juanp/Desktop/actividad-DataLake-DataWarehouse
```

**Todos los comandos de esta guía se corren dentro de WSL**, desde esa carpeta, salvo donde diga "en el compadre" (la EC2) o "en la consola de AWS".

---

## Punto 0: Preparación

### 0.1 Revisar las herramientas

```bash
terraform version
aws --version
aws sts get-caller-identity --profile user_cli
```

Debe responder la cuenta `112188880548` y el usuario `user_cli`.

📸 **`Punto 0 Identidad user_cli.png`**: la terminal con la salida de `aws sts get-caller-identity --profile user_cli`.

### 0.2 Darle a `user_cli` los permisos de IAM que faltan

Tu usuario `user_cli` ya tiene las políticas de la actividad anterior (secretos, S3, EC2, RDS, DocumentDB, Redshift). Falta una para crear los roles de la EC2: [`iam/05_user_cli_dw_roles_ec2.json`](iam/05_user_cli_dw_roles_ec2.json).

Esto se hace en la **consola de AWS con tu usuario administrador** (user_cli no puede darse permisos a sí mismo):

1. IAM → **Políticas** → **Crear política** → pestaña **JSON**.
2. Pega el contenido de `iam/05_user_cli_dw_roles_ec2.json`.
3. Nombre: `user_cli-dw-roles-ec2` → **Crear**.
4. IAM → **Usuarios** → `user_cli` → **Agregar permisos** → adjunta esa política.

📸 **`Punto 0 Política DW.png`**: la política creada, con el JSON visible.
📸 **`Punto 0 Políticas de user_cli.png`**: la pestaña de permisos de `user_cli` con las políticas adjuntas.

### 0.3 Llave SSH y tu IP

```bash
ssh-keygen -t ed25519 -f ~/.ssh/la-llave-dw -N ""
curl -s https://checkip.amazonaws.com
```

La llave **privada** (`la-llave-dw`) nunca se sube a ningún lado; solo la pública (`la-llave-dw.pub`) va a AWS. Anota tu IP: va en el siguiente paso.

### 0.4 Variables de Terraform

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
nano terraform/terraform.tfvars
```

Cambia `mi_ip_cidr` por tu IP con `/32` (ejemplo: `"190.240.73.151/32"`). Guarda con `Ctrl+O`, Enter, y sal con `Ctrl+X`. Los cuatro interruptores `crear_*` quedan en `false` por ahora.

> ⚠️ **Regla de oro de los interruptores:** si pones un `crear_*` en `false` después de haberlo creado, el siguiente `terraform apply` **destruye** ese recurso. **Siempre lee el plan** antes de escribir `yes`.

### 0.5 Inicializar Terraform

```bash
cd terraform
terraform init
terraform validate
```

Debe decir `Terraform has been successfully initialized!` y `The configuration is valid.`

📸 **`Punto 0 Terraform Init.png`**: la salida de `terraform init`.

---

## Punto 1: Red, bodega y roles (no cuestan)

Se crean siempre: la VPC con sus 3 subredes, el bucket de S3 y los dos roles de IAM.

```bash
terraform plan
terraform apply
```

Lee el plan (debe mostrar `Plan: ~24 to add, 0 to change, 0 to destroy`) y escribe `yes`.

**Debes ver:** `Apply complete! Resources: ... added.` y, en `Outputs`, el nombre del bucket.

📸 **`Punto 1 Terraform Plan.png`**: la línea `Plan: N to add...`.
📸 **`Punto 1 Terraform Apply.png`**: `Apply complete!` y los outputs.

En la **consola de AWS** (región Ohio):
📸 **`Punto 1 VPC Barrio.png`**: VPC → `el-barrio-dw`, con el mapa de recursos (3 subredes, tabla de rutas, Internet Gateway).
📸 **`Punto 1 S3 Bodega.png`**: S3 → bucket `la-bodega-del-pelao-dw-112188880548`, pestaña **Propiedades** (versionado activado) y **Permisos** (bloqueo de acceso público activado). Puedes tomar dos capturas.
📸 **`Punto 1 Roles IAM.png`**: IAM → Roles → busca `la-picotera` y `el-compadre`: deben aparecer los dos roles.

---

## Punto 2: El compadre (EC2 con Docker)

1. Edita `terraform/terraform.tfvars` y pon `crear_ec2 = true`.
2. Aplica:

```bash
terraform apply
```

El plan debe mostrar solo recursos nuevos (la llave y la EC2). Escribe `yes`.

3. Vuelve a la raíz del proyecto y espera unos 3 minutos a que termine el arranque (instala Docker). Luego pregúntale al compadre cómo va:

```bash
cd ..
bash scripts/aws/compadre.sh estado
```

Debe decir `El compadre esta LISTO.` y mostrar las versiones de Docker y Docker Compose. Si dice que todavía se está armando, espera un minuto y repite. (La primera vez pregunta si confías en el host: ya lo acepta solo.)

Si quieres entrar al compadre para mirar: `bash scripts/aws/compadre.sh entrar` (y `exit` para salir).

📸 **`Punto 2 EC2 Consola.png`**: EC2 → Instancias → `el-compadre-dw` en estado `En ejecución`.
📸 **`Punto 2 EC2 Portero.png`**: la pestaña **Seguridad** de la instancia: reglas de entrada (22 y 8080 solo desde tu IP).
📸 **`Punto 2 EC2 Docker.png`**: la terminal con la salida de `compadre.sh estado`.

> **Desde aquí te quedas en la raíz del proyecto.** Los `terraform apply` los corres con `terraform -chdir=terraform apply`.

---

## Punto 3: El sancocho (RDS MySQL)

1. En `terraform.tfvars`: `crear_rds = true`.
2. `terraform -chdir=terraform apply` → `yes`. Tarda unos 8 a 12 minutos.

📸 **`Punto 3 Terraform Apply RDS.png`**: el `Apply complete!`.
📸 **`Punto 3 RDS Consola.png`**: RDS → Bases de datos → `el-sancocho-dw`, estado `Disponible`; muestra el motor MySQL y que **no es de acceso público**.
📸 **`Punto 3 Secreto RDS.png`**: Secrets Manager → el secreto que empieza por `rds!db-`. **No muestres el valor de la clave.**

**Probar la conexión** (desde la raíz del proyecto; el atajo copia el script al compadre, instala lo necesario, lee el endpoint y la clave solos, y no imprime la clave):

```bash
bash scripts/aws/compadre.sh probar rds
```

**Debes ver:** `RDS MySQL -> version=8.4.x usuario=pelao_admin@... base=ecommerce`.

📸 **`Punto 3 Prueba RDS.png`**: esa línea en la terminal.

---

## Punto 4: El bololo (DocumentDB)

1. En `terraform.tfvars`: `crear_docdb = true`.
2. `terraform -chdir=terraform apply` → `yes`. Tarda unos 10 a 15 minutos.

📸 **`Punto 4 Terraform Apply DocumentDB.png`**: el `Apply complete!`.
📸 **`Punto 4 DocumentDB Consola.png`**: Amazon DocumentDB → Clústeres → `el-bololo-dw`, con su instancia `el-bololo-dw-nodo-1` disponible.

**Probar la conexión** (el atajo también descarga el certificado TLS en el compadre):

```bash
bash scripts/aws/compadre.sh probar docdb
```

**Debes ver:** `DocumentDB -> ping ok, version=5.0.0, bases=[...]`.

📸 **`Punto 4 Prueba DocumentDB.png`**: esa línea en la terminal.

> **Diferencias con MongoDB que ya están contempladas:** DocumentDB exige TLS (por eso el certificado), no soporta `retryWrites` (el script usa `retryWrites=False`) y no es MongoDB: algunos operadores como `$where` no existen. Esto se documenta en el Word.

---

## Punto 5: La picotera (Redshift Serverless)

1. En `terraform.tfvars`: `crear_redshift = true`.
2. `terraform -chdir=terraform apply` → `yes`. Tarda unos 5 minutos.

📸 **`Punto 5 Terraform Apply Redshift.png`**: el `Apply complete!`.
📸 **`Punto 5 Redshift Workgroup.png`**: Redshift Serverless → Workgroup `la-picotera-dw-wg` (4 RPU).
📸 **`Punto 5 Redshift Namespace.png`**: el namespace `la-picotera-dw` con el rol `la-picotera-lee-la-bodega` asociado.

**Probar la conexión:**

```bash
bash scripts/aws/compadre.sh probar redshift
```

📸 **`Punto 5 Prueba Redshift.png`**: la salida con la base y la versión.

**Query Editor v2** (consola de AWS):
1. Amazon Redshift → **Query editor v2** → conéctate a `la-picotera-dw-wg` con **AWS Secrets Manager** y el secreto del namespace.
2. Corre `SELECT current_database(), current_user, version();`

📸 **`Punto 5 Query Editor.png`**: la consulta y su resultado.

---

## Punto 6: Desplegar el pipeline en el compadre y cargar las fuentes

Necesitas los cuatro `crear_*` en `true` (EC2, RDS, DocumentDB y Redshift). Todo se corre desde la raíz del proyecto.

### 6.1 Llevar el código y levantar Airflow

```bash
bash scripts/aws/compadre.sh desplegar
```

Empaqueta `docker/` y `src/`, los copia al compadre, construye la imagen de Airflow (con `dbt-redshift`) y la levanta. La primera vez tarda unos minutos. Debe terminar con `Listo. Airflow: http://<IP>:8080`.

📸 **`Punto 6 Despliegue.png`**: el final de la salida, con la URL de Airflow.

### 6.2 Entrar a Airflow

```bash
bash scripts/aws/compadre.sh clave-airflow
```

Te muestra la clave del usuario `airflow` (se generó dentro del compadre; no está en el repositorio). Abre `http://<IP>:8080` en el navegador y entra. Solo tu IP puede abrirlo.

📸 **`Punto 6 Airflow DAG.png`**: la lista de DAGs con `ecommerce_dw_aws`. **No captures la clave.**

### 6.3 Cargar los datos en RDS y DocumentDB

```bash
bash scripts/aws/escenarios.sh reiniciar
```

Escribe `si`. Deja Redshift y la bodega en cero (borra lo que quedó de pruebas anteriores) y genera los datos sintéticos de DE-DW (semilla 42) directamente en RDS y DocumentDB. Debe terminar con:

```
MySQL: 50 customers, 25 products, 100 orders, 253 order items
MongoDB: 150 reviews, 500 navigation events; seed=42
Injected bad rows: 34 ...
```

📸 **`Punto 6 Fuentes.png`**: esas tres líneas.

> **Ajuste MongoDB → DocumentDB:** el generador crea las colecciones con validadores `$jsonSchema`, que DocumentDB no soporta. En AWS se crean sin validador (variable `MONGO_SIN_VALIDADOR`) y la calidad la revisa dbt en la cuarentena. Además la conexión usa TLS con el certificado `global-bundle.pem`, `retryWrites=false` y `directConnection=true`.

---

## Punto 7: Carga inicial (Airflow → S3 → Redshift → dbt)

```bash
bash scripts/aws/escenarios.sh carga-inicial
```

Dispara el DAG `ecommerce_dw_aws` y espera. Tarda unos 3 minutos. Al final muestra el lote en `ops.lotes` (modo `completo` o `foto`, estado `procesado`) y los conteos: `fct_sales 253`, `fct_reviews 150`, `fct_navigation_events 500`, `dim_customer 50`, `dim_product 25`.

📸 **`Punto 7 Carga Inicial.png`**: la salida de la terminal.

**En Airflow** (`http://<IP>:8080` → `ecommerce_dw_aws` → **Grid**):
📸 **`Punto 7 Airflow Grid.png`**: la corrida con las 12 tareas en verde.
📸 **`Punto 7 Airflow Graph.png`**: la pestaña **Graph**, con las dependencias.
📸 **`Punto 7 dbt test.png`**: clic en `dbt_test` → **Logs**, donde se ve `Done. PASS=97 WARN=0 ERROR=0`.
📸 **`Punto 7 Log Lote.png`**: el log de `cargar_a_redshift`, donde aparecen las líneas `[lote=... entidad=...] COPY ok`.

**En la consola de AWS:**
📸 **`Punto 7 S3 Lote.png`**: S3 → `la-bodega-del-pelao-dw-...` → `raw/mysql/orders/` → la carpeta `batch_id=...` con `orders.csv.gz` y `_manifest.json`.
📸 **`Punto 7 S3 Manifiesto.png`**: abre `_manifest.json` (Acciones → Abrir), que muestra fecha de extracción, `batch_id` y número de filas.
📸 **`Punto 7 Redshift Tablas.png`**: Query Editor v2 → base `ecommerce_dw`, con los esquemas `raw`, `intermediate`, `quarantine`, `marts` y `ops` desplegados.

**Cómo se identifica un lote y cuándo avanza:** cada corrida crea un `batch_id` (fecha UTC, por ejemplo `20261026T153000Z`). En `ops.lotes` cada entidad pasa por `extraido` (archivo en S3) → `cargado` (`COPY` y conteo verificados) → `procesado` (dbt y pruebas OK). La marca de avance (`marca_superior`) solo la usa el siguiente lote si quedó `cargado` o `procesado`.

> **Ojo en el Query Editor:** `raw` es palabra reservada de Redshift. Para consultarlo escríbelo entre comillas: `select * from "raw".mysql_orders limit 10;`

---

## Punto 8: Calidad, incrementalidad y recuperación

Cada comando corre el escenario e imprime el **antes y el después**. Toma la captura de la terminal al terminar cada uno. Hazlos **en este orden**.

| # | Comando | Qué demuestra | Captura |
|---|---|---|---|
| 1 | `bash scripts/aws/escenarios.sh defectuosos` | Rechazos con motivo, lote de origen y fuente | `Punto 8 Defectuosos.png` |
| 2 | `bash scripts/aws/escenarios.sh repetir-lote` | Reprocesar el último lote no duplica hechos ni versiones | `Punto 8 Repetir Lote.png` |
| 3 | `bash scripts/aws/escenarios.sh nuevo-lote 1` | Lote incremental: solo trae lo nuevo y los hechos crecen | `Punto 8 Nuevo Lote.png` |
| 4 | `bash scripts/aws/escenarios.sh cambio-scd2` | SCD tipo 2: versión nueva vigente y cierre de la anterior | `Punto 8 SCD2.png` |
| 5 | `bash scripts/aws/escenarios.sh fallo` | Agrega el lote diario 2 y la carga falla a propósito (2 reintentos); no queda nada a medias | `Punto 8 Fallo.png` |
| 6 | `bash scripts/aws/escenarios.sh recuperar` | Reejecuta el lote fallido desde S3, sin pérdida ni duplicación | `Punto 8 Recuperacion.png` |
| 7 | `bash scripts/aws/escenarios.sh conciliar` | Ventas: origen válido = `fct_sales` = mart de QuickSight | `Punto 8 Conciliacion.png` |
| 8 | `bash scripts/aws/escenarios.sh lotes` | Historia de todos los lotes en `ops.lotes` | `Punto 8 Tabla Lotes.png` |

En Airflow, después del escenario 5:
📸 **`Punto 8 Airflow Fallo.png`**: la corrida en rojo, con `cargar_a_redshift` fallida y sus 3 intentos.

**Qué es el fallo controlado:** el DAG tiene el parámetro `simular_fallo`. Con el valor `cargar_a_redshift`, la carga hace los `COPY` y lanza un error **antes** de confirmar la transacción. Redshift deshace todo, así que `raw` no queda con un lote a medias y la marca de avance no se mueve. Para recuperar se dispara el DAG con `reprocesar_lote=<batch_id>`: vuelve a cargar desde S3 (sin tocar las fuentes) y corre dbt.

**Cómo identificar y recuperar una ejecución fallida en la vida real:**
1. En Airflow, la corrida queda en rojo y la tarea fallida dice en su log `[lote=<batch_id> tarea=<tarea>] FALLO: ...`.
2. En Redshift: `select * from ops.lotes where error is not null;` muestra el lote, hasta dónde llegó (`estado`) y por qué falló.
3. Se corrige la causa y se reprocesa: `bash scripts/aws/compadre.sh pipeline auto <batch_id>` (o en Airflow, **Trigger DAG w/ config** con `reprocesar_lote`).

---

## Punto 9: Dashboard en QuickSight

> AWS renombró QuickSight como **Amazon Quick**. En la consola puede aparecer con cualquiera de los dos nombres; es el mismo servicio.

QuickSight se cobra por usuario al mes. Al registrarte revisa el precio y si tu cuenta tiene prueba gratis; **al terminar el taller cancela la suscripción** (QuickSight → Manage QuickSight → Account settings → Unsubscribe).

### 9.1 Activar QuickSight (consola, una sola vez)

1. Busca **QuickSight** en la consola y regístrate (**Sign up**), en la región **US East (Ohio)**.
2. En los permisos de QuickSight, marca **Amazon Redshift**.

📸 **`Punto 9 QuickSight Cuenta.png`**: la pantalla de QuickSight ya activo.

### 9.2 (Recomendado) Usuario de solo lectura para QuickSight

En Query Editor v2, conectado a `ecommerce_dw`, crea un usuario que **solo puede leer `marts`**. Cambia la clave por una tuya (mínimo 8 caracteres, con mayúscula, minúscula y número):

```sql
create user quicksight_lector password 'CambiaEsta1';
grant usage on schema marts to quicksight_lector;
grant select on all tables in schema marts to quicksight_lector;
alter default privileges in schema marts grant select on tables to quicksight_lector;
```

Así el dashboard no usa la cuenta de administrador y no puede ver `raw` ni modificar nada.

### 9.3 Conjunto de datos

1. QuickSight → **Datasets** → **New dataset** → **Redshift (manual connect)**.
2. Datos de conexión (salen de `terraform -chdir=terraform output`):
   - **Database server:** el valor de `redshift_endpoint`
   - **Port:** `5439` · **Database name:** `ecommerce_dw`
   - **Username / Password:** `quicksight_lector` y la clave que elegiste
3. Elige el esquema **`marts`** y la tabla **`mart_ventas_diarias`**.
4. Escoge **Directly query your data**. Con consulta directa el dashboard siempre muestra lo último y no hay que refrescar nada después de un lote nuevo.

📸 **`Punto 9 Dataset.png`**: el dataset creado sobre `marts.mart_ventas_diarias`.

> **Si prefieres SPICE:** los datos se copian a QuickSight y **no se actualizan solos**. Después de cada lote ve a Datasets → `mart_ventas_diarias` → **Refresh now** (o programa un refresco). Esto hay que documentarlo si lo usas.

### 9.4 El dashboard (tres elementos mínimos)

Crea un **Analysis** con el dataset y agrega:

1. **Gráfica de ventas:** un *Vertical bar chart* con `fecha` en el eje X (agrupado por mes), `ventas_totales` (Sum) como valor y `categoria` como color.
2. **Indicador de ventas totales:** un *KPI* con `ventas_totales` (Sum).
3. **Filtro:** agrega un filtro por `canal` y, en el panel de filtros, **Add to sheet** para que quede como control desplegable.

Publica: **Share → Publish dashboard**, con el nombre `La picotera de ventas`.

📸 **`Punto 9 Dashboard.png`**: el dashboard completo.
📸 **`Punto 9 Dashboard Filtrado.png`**: el mismo con el filtro en `web`.

### 9.5 Verificar el indicador con SQL

En Query Editor v2, la suma total debe coincidir con el KPI sin filtro:

```sql
select sum(ventas_totales) as ventas_totales from marts.mart_ventas_diarias;
```

Y con el filtro de canal en `web`:

```sql
select sum(ventas_totales) as ventas_web from marts.mart_ventas_diarias where canal = 'web';
```

📸 **`Punto 9 SQL Indicador.png`**: las dos consultas con su resultado, junto al KPI del dashboard. Deben ser el mismo número con el mismo filtro y la misma fecha de actualización.

### 9.6 Demostración: un lote nuevo hasta el dashboard

```bash
bash scripts/aws/escenarios.sh nuevo-lote 3
```

Recarga el dashboard: el KPI sube en el valor de las ventas nuevas (con consulta directa, sin refrescar nada). Repite la consulta del 9.5 para ver que coincide.

📸 **`Punto 9 Lote Nuevo Dashboard.png`**: el KPI actualizado.

---

## Punto 10: Eliminación y verificación

Cuando termines **todo** el taller (incluidos los Puntos 6 al 9 del siguiente bloque), desde la raíz del proyecto:

```bash
bash destruir_todo.sh
```

El script te muestra qué se va a borrar, te pide escribir `si`, borra con Terraform y al final corre `verificar_limpieza.sh` solo.

**Debe terminar con `TODO LIMPIO` y todos los bloques en `(vacio)`.** Si queda algo, el script te lo dice: repítelo (es seguro) o bórralo en la consola.

📸 **`Punto 10 Destroy.png`**: `Destroy complete! Resources: N destroyed.`
📸 **`Punto 10 Verificacion Limpieza.png`**: la salida de `verificar_limpieza.sh` con `TODO LIMPIO`.

### Si cortas por el día (apagar solo lo caro)

```bash
bash destruir_todo.sh --solo-lo-caro
```

Apaga la EC2, RDS, DocumentDB y Redshift, y deja la red, la bodega con sus archivos y los roles (no cuestan). Al día siguiente pones los `crear_*` en `true` y corres `terraform -chdir=terraform apply`. Los datos que estén dentro de las bases se pierden; los de S3 no.

### Revisar sin borrar nada

```bash
bash verificar_limpieza.sh
```

Solo lee la cuenta y te dice si queda algo cobrando. Úsalo cuando dudes, también si Terraform perdió su estado.

---

## Costos aproximados (Ohio, estimación)

| Servicio | Cómo cobra |
|---|---|
| Red, S3 casi vacío, roles | Casi nada |
| EC2 `t3.large` (el compadre) | Por hora encendida |
| RDS `db.t4g.micro` | Por hora encendida |
| DocumentDB Serverless (mínimo 0,5 DCU) | Por hora encendida, de lo más caro por hora |
| Redshift Serverless (4 RPU) | Solo mientras corren consultas |
| QuickSight | Mensualidad por usuario (revisa si tu cuenta tiene prueba gratis) |

Precios exactos: calculadora oficial de AWS. Lo importante: **no dejar nada encendido** al terminar.

## Errores comunes

- **`AccessDenied` al aplicar:** copia el mensaje completo; casi siempre es un permiso que le falta a `user_cli`. Pásamelo y ajusto la política.
- **`error reading public key`:** falta la llave. Repite el paso 0.3.
- **El SSH no conecta:** tu IP cambió. Corre `curl -s https://checkip.amazonaws.com`, actualiza `mi_ip_cidr` y haz `terraform apply`.
- **`terraform apply` quiere destruir algo:** pusiste un `crear_*` en `false` sin querer. Cancela (`no`) y revisa `terraform.tfvars`.
- **`compadre.sh` dice que el compadre no está prendido:** falta `crear_ec2 = true` y el `terraform apply` del Punto 2.
- **`verificar_limpieza.sh` muestra `??  SIN PERMISO`:** falta adjuntar la política `iam/05` a `user_cli` (Punto 0.2).
