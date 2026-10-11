# AI Development Harness — Core interno

Herramienta de desarrollo que prepara la orquestación de proyectos convencionales.
La versión interna **0.17.0** añade evaluaciones AI e informes de preparación para producción y permite elegir local, GCP o Azure al iniciar un proyecto,
con infraestructura Terraform para rutas DEV stateless, tras la definición de producto
y prototipos navegables: configuración, validación,
selección determinista de arquitectura y generación de proyectos React/FastAPI
standalone, arquitectura hexagonal, persistencia, proveedores AI y pruebas de contratos.
Incluye ejecución en memoria y Taskiq/Redis, CLI de tareas registradas, administración
autenticada de horarios y trazas web/API, logs JSON y métricas. Las limitaciones de cada
fase se recogen en sus informes.
No instala dependencias ni despliega recursos automáticamente.
El nombre `harness` es provisional; este paquete no está destinado a publicación.

## Evaluaciones AI y preparación para producción (fase 17)

Cada proyecto generado incluye `PRODUCTION_READINESS.md` con revisión de seguridad,
backups/restauración, migraciones, monitorización, rendimiento y rollback GCP/Azure.
`scripts/performance_baseline.py` mide peticiones secuenciales locales a health;
no sustituye una prueba de carga en staging.

Los proyectos AI incluyen `evals/smoke.json` y `app.infrastructure.ai_evals`:
dataset sintético, evaluación reproducible, hook de grader y reportes sin prompts
ni respuestas. Desde el servicio API:

```bash
AI_PROVIDER=fake python -m app.infrastructure.ai_evals evals/smoke.json
```

El fake debe estar habilitado. Los proveedores reales requieren `--live` y una
revisión previa del dataset/coste; los ejemplos sintéticos no miden calidad de modelos.
Los datasets de ejemplo se incorporan a la imagen de desarrollo, no a la de producción.

```bash
harness readiness --project mi-proyecto > production-readiness.json
```

Este comando no modifica el proyecto. Bloquea evidencias ausentes, fallidas, inválidas,
con más de 30 días o vinculadas a otro manifiesto. Los registros son declaraciones
del operador: incluso con todas presentes exige revisión independiente y nunca
autoriza un despliegue. La guía generada describe su formato. Sale con código 1
si hay bloqueos y 0 si el inventario está completo para revisión.

Ver [fase 17](docs/phase-17-report.md) y el
[informe de producción del ejemplo](docs/phase-17-production-readiness.md).
La implementación del roadmap inicial está entregada; la certificación operativa
de cada proyecto y entorno requiere sus propias pruebas y evidencias.

## Actualizaciones (fase 16)

`harness update` propone migrar un proyecto generado al bundle fijado de la versión
de Harness instalada. No consulta ni instala versiones `latest`. Requiere un
repositorio Git limpio, con los archivos gestionados versionados y `project.yaml`
sin cambios desde la generación. Esta primera ruta admite `fullstack-ai-skeleton`;
los prototipos de producto y cambios de arquitectura necesitan una migración específica.

```bash
harness update --project ./mi-proyecto --checks ./checks.json > propuesta.json
# Revisar rutas, hashes y los cuatro comandos incluidos en la propuesta.
harness update --project ./mi-proyecto --checks ./checks.json \
  --apply --approve HASH_DE_LA_PROPUESTA --worktree ./mi-proyecto-actualizado
```

`checks.json` es un objeto con cuatro claves obligatorias: `dependencies`, `tests`,
`contracts` y `e2e`. Cada una contiene `cwd` relativo al proyecto y `argv` como
lista de argumentos. Por ejemplo, `{"cwd":".","argv":["make","test"]}` para
`tests`. La receta concreta depende del proyecto: debe instalar o construir las
dependencias fijadas y ejecutar pruebas reales, incluyendo su flujo E2E.
Hay un ejemplo reproducible en `scripts/smoke_update.py`.

La aprobación incluye los comandos y autoriza su ejecución como código local de
confianza, con el entorno del proceso. No pongas credenciales en los argumentos:
el plan los muestra y conserva. Estos comandos deben limitarse a validación local;
el motor no puede demostrar que un comando llamado «tests» tenga cobertura real
ni aislar código arbitrario. No utilices recetas de despliegue o migraciones de PROD.

La aplicación crea una rama `harness-update-*` y un worktree separado. Los cambios
que colisionan con modificaciones del usuario se rechazan. Las modificaciones
ajenas a la actualización se preservan. Después ejecuta los cuatro pasos y doctor,
comprueba que los pasos no alteraron archivos gestionados y escribe
`.harness/update-report.json`. Un fallo deja el candidato disponible para inspección.
El resultado satisfactorio es `ready-for-human-review`: no hace commit, merge,
push, despliegue ni cambios de base de datos por su cuenta. El original sigue intacto.
Doctor puede conservar comprobaciones externas pendientes; figuran en el informe.

Ver [informe de fase 16](docs/phase-16-report.md).

## Diagnóstico (fase 15)

`harness doctor --project mi-proyecto` inspecciona configuración, manifiesto,
código de entrada, dependencias frontend y configuración CI sin modificar archivos.
`--json` produce un informe estructurado; `--strict` falla también ante advertencias
o comprobaciones pendientes. Los códigos de salida son 0 sin fallos comprobados,
1 con fallos y 2 con problemas de uso o resultados pendientes en modo estricto.

`--runtime --api-url http://127.0.0.1:8000 --web-url http://127.0.0.1:5173`
añade peticiones GET locales y observaciones Docker del proyecto seleccionado.
Puede descubrir las direcciones desde `.harness/preview.json`. No arranca servicios,
ejecuta código de aplicación, sigue redirecciones ni muestra cuerpos o logs sensibles.
Los GET pueden quedar registrados en los logs del servicio.

`--fix` muestra las reparaciones propuestas sin escribir. `--fix --approve`
restaura únicamente archivos ausentes reproducibles con la misma versión y
configuración, registrando su estado anterior ausente en `.harness/doctor-backups/`.
No sobrescribe archivos modificados ni actualiza plantillas antiguas.

Los proyectos nuevos incluyen las skills `backend-diagnose`, `frontend-diagnose`
y `browser-inspect` en `skills/`. La última reutiliza las herramientas del host.
Credenciales reales, migraciones aplicadas, recursos cloud y protecciones GitHub
quedan explícitamente sin verificar cuando no hay evidencia suficiente.
Ver [alcance y pruebas de fase 15](docs/phase-15-report.md).

## CI/CD (fase 14)

Cada scaffold incluye GitHub Actions para lint, pruebas y contratos, builds y
auditoría de dependencias. Los proyectos cloud añaden validación Terraform,
despliegue DEV desde develop y PROD exclusivamente manual desde main.
Los despliegues están desactivados por defecto y usan OIDC e imágenes por digest.
PROD comprueba mediante la API que el Environment tiene revisores, prevención
de autoaprobación, bloqueo de bypass administrativo y restricción a main.

El archivo generado `CI_CD.md` detalla variables, permisos, runners y límites.
Azure necesita un runner aislado con acceso al entorno interno. Terraform sigue
gestionando infraestructura; CI/CD gestiona la imagen de un servicio ya existente.
No se ejecuta apply de infraestructura automáticamente. PROD requiere recursos
propios provisionados y una imagen revisada ya publicada en su registro.

Validación local reproducible de los workflows:

```bash
python scripts/smoke_cicd.py --actionlint /ruta/actionlint --output output/ci-check
```

Requiere actionlint 1.7.12. Generar workflows no configura GitHub ni equivale a
haber probado un despliegue remoto. Ver [informe de fase 14](docs/phase-14-report.md).

## Selección de entorno e infraestructura DEV (fase 13)

```bash
harness init configuracion --name mi-proyecto --environment azure
harness scaffold configuracion/project.yaml --output mi-proyecto
# Alternativas: --environment local o --environment gcp
```

La selección explícita en `init` prepara un proyecto fullstack React/FastAPI
generable. Sin ese argumento, `init` conserva su configuración mínima histórica.
`setup` también admite `--environment` o el campo `environment` del YAML de
especificación; pregunta por él al configurar un proyecto nuevo interactivamente.
Si se omite al actualizar, conserva la selección existente. Una selección cloud
añade Terraform y OpenTelemetry; rechaza capacidades no soportadas antes de escribir.

| Entorno | Estado | Acceso cloud inicial |
| --- | --- | --- |
| Local | Implementado | Compose local, sin infraestructura cloud |
| GCP | Experimental | Cloud Run con invocación IAM |
| Azure | Experimental | Container Apps con ingress interno al entorno |
| AWS | Pendiente | Selección ejecutable rechazada explícitamente |

Azure no incluye todavía acceso público desde el navegador ni login Entra ID;
el aislamiento de red no equivale a autenticación de usuarios. Los proveedores
comparten el contenedor, pero conservan sus requisitos de recursos y seguridad.

Para revisar una nueva selección: `harness setup --project configuracion/project.yaml
--environment gcp`. La escritura requiere `--write --approve` tras revisar el diff.
Esto cambia configuración: no migra aplicaciones desplegadas, datos o estados
Terraform. El scaffold genera en un directorio nuevo, sin sobrescribir proyectos.

`harness scaffold examples/cloud/project.yaml --output output/cloud-demo` genera
un contenedor web/API y dos módulos Terraform: Artifact Registry y Cloud Run.
El servicio exige IAM, imagen por digest y cuenta de ejecución dedicada.
`infra/workload.json` describe la carga con un esquema independiente del proveedor.
La primera ruta es stateless; persistencia, jobs y otros proveedores cloud quedan
fuera de estos renderers y se rechazan explícitamente. AWS sigue planificado.
El ejemplo Azure está en `examples/cloud-azure/project.yaml`.

El README generado explica planes, permisos, despliegue y retirada manuales.
`python scripts/smoke_cloud.py --output output/cloud-check` verifica Terraform y
el contenedor local, sin desplegar. Se han probado planes estructurales offline;
IAM, cuotas, facturación y despliegue real requieren un proyecto GCP autorizado.
Consulta [el informe de fase 13](docs/phase-13-report.md).
Para Azure, añade `--provider azure` al smoke: sus planes usan proveedor simulado;
un plan AzureRM autenticado sigue pendiente. Consulta
[la ampliación multiproveedor](docs/phase-13-multicloud-report.md).

## Instalación y uso

Requiere Python 3.12–3.14 y uv. La escritura usa protección de rutas específica de POSIX
(macOS/Linux); Windows no está soportado. Las plataformas realmente verificadas
se documentan en `docs/phase-2-report.md`.

```bash
uv sync --locked
uv run --locked harness --help
uv run --locked harness init ./mi-proyecto --name mi-proyecto
uv run --locked harness validate ./mi-proyecto/project.yaml
uv run --locked harness setup examples/specifications/fullstack-ai/spec.yaml
```

En este workspace uv está instalado localmente: sustituye `uv` por `.tools/bin/uv`
y usa `UV_CACHE_DIR=.uv-cache` si no puedes escribir en la caché del usuario.
El lock contiene las versiones exactas; `sync --locked` no las actualiza.

`init` crea únicamente `project.yaml`, valida el nombre antes de escribir y nunca
sobrescribe un archivo existente. Rechaza rutas con `..` o enlaces simbólicos,
incluidos los directorios intermedios. En macOS, usa `/private/tmp` en vez del
alias `/tmp` para destinos absolutos. `validate` no modifica el proyecto, no usa
red y no consulta credenciales. Un resultado válido confirma solo el esquema y
sus reglas cruzadas: **no certifica soporte operativo ni salud del runtime**.

Los códigos de salida son 0 (éxito), 1 (configuración/operación fallida) y 2
(uso incorrecto). Los resultados van a stdout y los errores a stderr, sin
volcar el contenido de la configuración.

## Selección de arquitectura

`setup` acepta YAML o un bloque `harness-spec` en Markdown. Sin archivo, pregunta
solo los datos de arquitectura que falten. En ejecuciones sin terminal, informa
de los campos ausentes y termina sin escribir. La propuesta se imprime como YAML
en stdout y su explicación en stderr; `--json` entrega un informe estructurado.

```bash
# Revisar una propuesta sin modificar archivos
uv run --locked harness setup examples/specifications/fullstack-ai/spec.yaml --json

# Guardar tras revisar; --approve permite aprobación explícita sin interacción
uv run --locked harness setup examples/specifications/fullstack-ai/spec.yaml --output ./demo/project.yaml --write --approve

# Preparar una actualización conservando las opciones existentes
uv run --locked harness setup cambios.yaml --project ./demo/project.yaml
uv run --locked harness setup cambios.yaml --project ./demo/project.yaml --write --approve
```

| Web | Servicios independientes | Ruta propuesta |
| --- | --- | --- |
| Sí | Ninguno | `simple-web` |
| No | Uno | `ai-service` |
| Sí | Uno | `fullstack-ai` |
| Opcional | Dos o más | `service-platform` |

La selección no depende de un LLM, una cuenta externa ni palabras clave del texto
libre. Las capacidades AI son opcionales incluso en rutas con `ai` en el nombre.
Consulta [el formato de especificación y las reglas](docs/setup.md).

`setup` muestra la propuesta antes de escribir y requiere confirmación o
`--approve`. Al actualizar el archivo indicado por `--project`, guarda una copia
exacta `project.yaml.backup-*` y comprueba que el original no haya cambiado.
Sin cambios semánticos, conserva el archivo byte a byte. Una actualización real
normaliza el YAML; comentarios y formato originales quedan en la copia.

## Generación de aplicaciones

```bash
uv run --locked harness scaffold examples/specifications/fullstack-ai/expected-project.yaml --output ./fullstack-demo --dry-run
uv run --locked harness scaffold examples/specifications/fullstack-ai/expected-project.yaml --output ./fullstack-demo
cd fullstack-demo
make up
make test
make test-contracts
make down
```

El destino debe ser nuevo. La generación acepta actualmente `fullstack-ai` con
una app React y un servicio FastAPI, con persistencia opcional.
`architecture.hexagonal_services: true` (por defecto) añade dominio, aplicación,
puertos, adaptadores, composición y tests de contratos; `false` genera una API
simple. El resultado funciona sin instalar el harness. Consulta el README y
`services/api/ARCHITECTURE.md` del proyecto generado.

La web está en `http://localhost:5173`, la API en `http://localhost:8000/api/health`
y la variante hexagonal expone `/api/readiness`. Docker y Make son necesarios para
estos comandos; el README generado también explica la ejecución sin Docker.

## Persistencia opcional

`database.provider` admite `memory`, `sqlite` y `postgres`. Para búsqueda vectorial,
añade `database.vector: pgvector` a PostgreSQL; para caché, `cache.provider: redis`.
Estas capacidades requieren `architecture.hexagonal_services: true`.

```bash
uv run --locked harness scaffold examples/persistence/project.yaml --output ./datos-demo
cd datos-demo
make migrate
make up
make test
make test-integration
make down
```

Se generan únicamente los adaptadores, dependencias y servicios seleccionados.
El repositorio clave/valor comparte contratos entre memoria, SQLite y PostgreSQL.
pgvector usa un puerto independiente con un ejemplo de tres dimensiones; Redis
almacena bytes con caducidad. Las migraciones Alembic son explícitas; el arranque
de la API no cambia el esquema. `make down` conserva los volúmenes de datos.
No se publican puertos de PostgreSQL ni Redis en el host.

`make test` omite los contratos externos si no recibe sus variables de conexión;
`make test-integration` los ejecuta contra los servicios de Compose seleccionados.
Consulta `services/api/PERSISTENCE.md` en el proyecto generado y el
[informe de fase 5](docs/phase-5-report.md) para alcance y limitaciones.

## Proveedores AI

Para AI, añade `ai.providers: [fake, openai, gemini, vertex]` o el subconjunto
necesario. [El ejemplo AI](examples/ai/project.yaml) arranca con fake sin claves.
OpenAI usa Responses; Gemini y Vertex usan modos separados del SDK Google Gen AI.
Cambiar `AI_PROVIDER` y las variables de modelo/credenciales no modifica el dominio.

```bash
uv run --locked harness scaffold examples/ai/project.yaml --output ./ai-demo
cd ai-demo
make up
make ai-check
printf 'Entrada de prueba' | make ai-generate
make test-contracts
make down
```

`make ai-check` solo valida configuración local. `make ai-check-remote` consulta
metadatos del modelo con las credenciales configuradas. `make ai-generate-live`
autoriza una generación real que puede tener coste. Modelos y credenciales son
explícitos; el scaffold no los busca ni realiza llamadas a los proveedores.
Las pruebas automatizadas usan SDKs reales y HTTP simulado; todavía no acreditan
acceso a cuentas reales. Consulta `services/api/AI.md` en el proyecto generado y
[el informe de fase 6](docs/phase-6-report.md).

## Configuración

Para añadir diagnósticos, selecciona `observability: {provider: opentelemetry}`.
El ejemplo `examples/observability/project.yaml` genera trazas web/API, logs JSON y
métricas con exportación local u OTLP. Consulta el [informe de fase 10](docs/phase-10-report.md)
y `services/api/OBSERVABILITY.md` en el proyecto generado.

Para generar el ejemplo de jobs y administración:

```bash
harness scaffold examples/jobs/project.yaml --output output/jobs-demo
cd output/jobs-demo
make up
harness jobs list
harness jobs run heartbeat
harness schedules list
```

Configura auth siguiendo `services/api/AUTH.md` para acceder a `/admin/schedules`.
Los horarios parten desactivados. `services/api/JOBS.md` explica el alcance de memoria,
Redis y las garantías de entrega. Evidencia: [informe de fase 9](docs/phase-9-report.md).

Consulta `examples/minimal/project.yaml` y `examples/fullstack/project.yaml`.
`schemas/project.schema.json` facilita autocompletado; las reglas entre secciones
(admin/auth, Taskiq/Redis, etc.) también requieren `harness validate`.

El esquema admite los cuatro golden paths del roadmap y bloques opcionales de
database, cache, AI, storage, auth, admin, jobs, scheduler, observability, cloud
e IaC. Admitir un identificador no significa disponer de su integración.
Persistencia, caché, AI, jobs, scheduler y observabilidad están en estado `experimental`; las demás capacidades del
catálogo permanecen `planned`.

`auth.authorization`: `authentication` (solo autenticación), `roles` (RBAC) o
`permissions` (RBAC con permisos). Admin parte desactivado y sin recursos
expuestos. Si se activa, exige auth y un servicio FastAPI. `validate` no añade
autenticación ni modifica opciones automáticamente.

No introduzcas secretos en `project.yaml`. No existen campos de credenciales,
interpolación de entorno ni ejecución de comandos. La configuración local
secreta futura usará `.env`, excluido de Git. El parser limita YAML a 256 KiB,
32 niveles y 10 000 nodos; rechaza aliases, merge keys, duplicados y etiquetas
Python. El Core todavía no detecta secretos escondidos en campos de texto.

## Desarrollo

```bash
make install
make test
make lint
make build
make smoke-wheel  # instalación aislada del wheel, sin red tras sync
make schema  # tras cambiar los modelos
uv run --locked python scripts/smoke_persistence.py  # nueve variantes, requiere Docker
uv run --locked python scripts/smoke_ai.py  # SDKs con HTTP simulado, requiere Docker
uv run --locked python scripts/smoke_jobs.py  # worker/scheduler reales, requiere Docker
uv run --locked python scripts/smoke_observability.py  # trazas web/API y métricas, requiere Docker
# En el entorno local:
make UV=.tools/bin/uv check
```

No hay comandos `doctor` ni `update` en esta fase.

## OpenSpec y Agent OS

En un proyecto generado nuevo:

```bash
harness integrations init --project output/mi-proyecto --dry-run
harness integrations init --project output/mi-proyecto
```

La instalación explícita requiere red, Node >=20.19.0, npm y Bash. Fija OpenSpec
1.13.2 con lock npm y Agent OS 3.0 al commit `475b0cac4c7c5cf2336ad5a663b691a6d3415e05`
con checksum. Ejecuta los instaladores oficiales localmente y conserva los comandos
de estándares de Agent OS; OpenSpec gestiona las especificaciones y los cambios.
No actualiza instalaciones existentes ni ejecuta modelos. Consulta `DEVELOPMENT_TOOLS.md`
en el proyecto generado y [el informe de fase 11](docs/phase-11-report.md).

Prueba real reproducible (el directorio de salida debe ser nuevo):

```bash
uv run --locked python scripts/smoke_integrations.py --output output/integrations-check
```

Consulta [el plan](docs/implementation-plan.md), [la arquitectura](docs/architecture.md),
[las dependencias](docs/dependencies.md), [la fase 2](docs/phase-2-report.md) y
[la fase 3](docs/phase-3-report.md), [la fase 4](docs/phase-4-report.md) y
[la fase 5](docs/phase-5-report.md), [la fase 6](docs/phase-6-report.md) y
[la fase 9](docs/phase-9-report.md).

## Diseño de producto y prototipo

El workflow convierte un brief estructurado en documentación y detecta decisiones
faltantes. La skill `src/harness/data/skills/project-design/SKILL.md` conecta el
trabajo del host con OpenSpec y Agent OS. No replica sus flujos ni se instala
globalmente. Para lenguaje natural o referencias visuales, el host interpreta
la entrada y prepara YAML con `schemas/product.schema.json`.

```bash
harness project-design examples/product-design/incomplete.yaml --json
# Código 2: devuelve solo decisiones pendientes; no inventa respuestas.
harness project-design examples/product-design/feedback.yaml --output output/product-definition
harness prototype output/product-definition/product.yaml --output output/product-demo --dry-run
harness prototype output/product-definition/product.yaml --output output/product-demo --approve
cd output/product-demo
make up
# http://127.0.0.1:5173
```

La ruta inicial soporta una colección con título, descripción y estados declarados,
listado, detalle y creación. Ofrece API real con OpenAPI, datos sintéticos en
memoria, navegación responsive y pruebas E2E Playwright. Rechaza formas de producto
e integraciones no implementadas, sin reducir silenciosamente la especificación.
Los constraints en texto y la dirección visual quedan documentados para revisión;
solo contenido, estados y color de acento se aplican automáticamente.

El prototipo es local y sin login; los datos se reinician con el proceso API.
No constituye un despliegue público ni implementación de producción.
`PROTOTYPE.md` explica cómo ejecutar Chromium contra los procesos reales.
Prueba reproducible completa con Docker y Node 24:

```bash
uv run --locked python scripts/smoke_prototype.py --output output/prototype-check
```

El resultado incluye logs, capturas de escritorio/móvil y evidencia bajo
`.harness/verification`. Consulta [el informe de fase 12](docs/phase-12-report.md).
