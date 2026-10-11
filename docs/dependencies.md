# Dependencias y reproducibilidad

Fases 15–17 usan la biblioteca estándar y las dependencias existentes del Core.
Doctor, actualización, readiness y las herramientas de evaluación no añaden un
runtime propietario al proyecto generado. Las evaluaciones usan el puerto AI y
SDKs ya fijados en fase 6; no incorporan un nuevo proveedor ni librería de evals.

Fase 14 incorpora herramientas de desarrollo, sin nuevas dependencias del Core:
actionlint 1.7.12 (MIT, descarga oficial con SHA-256 verificado), pip-audit 2.10.1
(Apache 2.0, lock separado con hashes) y npm audit del Node existente.
Las acciones se fijan por commit en `harness.cicd.ACTIONS`: checkout 7.0.1,
setup-python 7.0.0, setup-node 7.1.0, setup-terraform 4.0.1, Azure/login 3.1.0
y los commits oficiales consultados de google-github-actions auth/setup-gcloud v3.
Los commits están incluidos en `.github/action-pins.json` de cada proyecto.
Las acciones de GitHub, Google y Azure usan sus licencias MIT/Apache 2.0 upstream.
No se afirma ejecución remota de esas acciones: se valida el YAML con actionlint
y la lógica de los helpers mediante pruebas locales. Consultar `phase-14-report.md`.

Versiones directas elegidas y probadas en fase 1. Se fija un conjunto explícito;
no se afirma que cada paquete sea la última versión disponible.
La fase 2 conserva estas dependencias y sus versiones; solo cambia la versión
del propio harness a 0.2.0 dentro del lock.

| Dependencia | Versión | Categoría | Necesidad |
| --- | --- | --- | --- |
| Pydantic | 2.12.5 | Runtime del harness | Modelos estrictos, reglas y JSON Schema |
| PyYAML | 6.0.3 | Runtime del harness | Parser YAML seguro con límites y duplicados controlados |
| Hatchling | 1.27.0 | Build | Wheel/sdist estándar y recursos del paquete |
| pytest | 9.0.2 | Desarrollo | Pruebas unitarias y CLI |
| Ruff | 0.14.14 | Desarrollo | Lint y formato |
| uv | 0.12.17 | Herramienta local | Entornos, resolución, lock, build e instalación aislada |

`argparse`, `logging`, `pathlib`, `importlib.resources` y las operaciones de
filesystem proceden de la biblioteca estándar. No hay SDKs cloud/AI ni
dependencias de aplicación web. pytest/Ruff no se instalan al consumir el wheel.

Las dependencias directas están fijadas en `pyproject.toml`; `uv.lock` fija también
las transitivas runtime/desarrollo con hashes. Hatchling está fijado en
`build-system.requires`; su entorno de build aislado lo resuelve uv. El lock de
proyecto no incluye las transitivas de ese entorno de build independiente.

La instalación local de uv se hizo con el método PyPI oficial en `.tools`, sin
cambiar el Python global. Para reproducirla desde cero:

```bash
python3 -m venv .tools
.tools/bin/python -m pip install uv==0.12.17
UV_CACHE_DIR=.uv-cache .tools/bin/uv sync --locked
```

Las actualizaciones serán deliberadas: cambiar versión, regenerar lock, ejecutar
pruebas/lint/build y revisar resultados. No ejecutar actualizaciones automáticas
a `latest`. `.tools`, entornos y cachés están excluidos de Git y del sdist mediante
la selección explícita de archivos de build.

Fuentes oficiales consultadas para los mecanismos utilizados:

- [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [uv project management](https://docs.astral.sh/uv/guides/projects/)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation)
- [Hatch build configuration](https://hatch.pypa.io/latest/config/build/)
- [pytest getting started](https://docs.pytest.org/en/stable/getting-started.html)
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)

La matriz `src/harness/data/compatibility.yaml` no reemplaza el lock del Core.
React, FastAPI y Docker Compose registran evidencia experimental del skeleton
en Linux/arm64 con Docker Desktop; las demás integraciones siguen pendientes.
No se declara compatibilidad general ni aptitud para producción.

## Dependencias del proyecto generado (fases 3–4)

El Core no importa estas dependencias. Se instalan únicamente en el proyecto
generado con `npm ci` y `pip --require-hashes`:

| Dependencia directa | Versión | Uso |
| --- | --- | --- |
| React / React DOM | 19.3.0 | UI web |
| Vite / plugin React | 8.3.0 / 6.1.1 | Desarrollo, proxy API y build |
| TypeScript / Prettier | 7.0.2 / 3.9.9 | Comprobación y formato web |
| FastAPI / Uvicorn | 0.141.1 / 0.53.0 | HTTP y servidor ASGI |
| Pydantic | 2.12.5 | DTOs HTTP |
| pytest / httpx / Ruff | 9.0.2 / 0.28.1 / 0.14.14 | Tests y lint API |

Las transitivas y paquetes de tipos están fijados en los locks empaquetados.
Node 24 y Python 3.12 usan imágenes Docker por digest. La fase 4 no añade
dependencias: dataclasses, Protocol, datetime y AST proceden de Python.
La combinación Starlette 1.7.0 / httpx 0.28.1 emite un aviso de deprecación
en TestClient; los tests pasan. Su actualización queda para una revisión
deliberada de dependencias, con regeneración de hashes y ejecución de suites.

## Persistencia opcional (fase 5)

| Dependencia | Versión fijada | Cuándo se incluye |
| --- | --- | --- |
| SQLAlchemy | 2.0.54 | SQLite o PostgreSQL; SQL parametrizado y motores |
| Alembic | 1.20.0 | SQLite o PostgreSQL; migraciones versionadas |
| psycopg con binary | 3.3.6 | PostgreSQL; driver sin compilador del host |
| redis-py | 8.1.0 | Redis; caché de bytes con TTL |

Memoria no añade paquetes. pgvector usa SQL explícito sobre psycopg, sin un SDK
adicional. Las versiones de servidor verificadas son PostgreSQL 17.11, pgvector
0.8.6 y Redis 8.2.10; las imágenes están fijadas por digest. SQLite 3.40.1 procede
de la imagen Python 3.12.14 de Debian Bookworm.

`src/harness/templates/persistence_locks` contiene cinco conjuntos de requisitos
runtime/dev (Redis, SQL, SQL+Redis, PostgreSQL y PostgreSQL+Redis). Sus inputs `.in`
fijan versiones directas y sus `.txt` fijan transitivas con hashes. El generador
copia el conjunto elegido sin resolver ni descargar paquetes. El script de
mantenimiento `scripts/lock_persistence.py --uv .tools/bin/uv` permite regenerarlos
explícitamente, conservando las constraints del skeleton; no se ejecuta al generar.

Fuentes oficiales consultadas:

- [Parámetros SQL de psycopg](https://www.psycopg.org/psycopg3/docs/basic/params.html)
- [Transacciones de psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Tutorial de Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [pgvector: operadores y soporte Docker](https://github.com/pgvector/pgvector)
- [Operaciones Redis en Python](https://redis.readthedocs.io/en/stable/examples/set_and_get_examples.html)

Los números publicados se comprobaron también en PyPI antes de resolver y los
paquetes instalados se verificaron en el contenedor. La matriz registra alcance
experimental; los tests locales no equivalen a validación de producción.

## Proveedores AI (fase 6)

| Dependencia | Versión fijada | Alcance |
| --- | --- | --- |
| openai | 3.19.0 | Adaptador Responses; únicamente si se selecciona OpenAI |
| google-genai | 2.25.0 | Gemini y/o Vertex con modos de cliente explícitos |
| httpx | 0.28.1 | Transporte síncrono explícito del adaptador Google |

Fake no añade dependencias. El SDK OpenAI 3.19.0 utiliza httpx2; los tests inyectan
su MockTransport correspondiente. Google admite el cliente httpx elegido por la
plantilla. Las transitivas (incluida Google Auth) quedan fijadas con hashes.

`ai_locks` contiene 18 conjuntos: los tres grupos de SDK (OpenAI, Google, ambos)
combinados con las seis bases de dependencias (sin persistencia externa, Redis,
SQL, SQL+Redis, PostgreSQL, PostgreSQL+Redis). `scripts/lock_ai.py` permite
regenerarlos explícitamente, sujeto a las constraints previas. No cambia el lock
de dependencias del Core ni ejecuta llamadas a proveedores.

Fuentes oficiales consultadas para esta implementación mediante OpenAI Docs y
documentación oficial de Google:

- [SDK OpenAI y Responses](https://developers.openai.com/api/docs/libraries)
- [Google Gen AI SDK, configuración HTTP y clientes Gemini/Vertex](https://googleapis.github.io/python-genai/)

Las versiones se verificaron en PyPI y en el entorno instalado. Los contratos se
ejecutan contra SDKs reales con HTTP simulado, no contra cuentas facturadas. La
matriz distingue esta evidencia de una prueba live de credenciales/modelos.

## Jobs y scheduler (fase 9)

| Dependencia | Versión fijada | Alcance |
| --- | --- | --- |
| taskiq | 0.12.6 | Registro de tareas, worker y scheduler |
| taskiq-redis | 1.2.3 | Redis Streams y backend de resultados |
| redis-py | 8.1.0 | Store de horarios registrados y transporte |
| starlette-admin | 1.0.1 | Solo cuando admin está seleccionado; formularios de horarios |

Memoria usa la biblioteca estándar. Los requisitos Taskiq se incluyen desde
`requirements-jobs.txt`, con hashes y constraints de las dependencias anteriores.
El script `scripts/lock_jobs.py --uv .tools/bin/uv` es una acción explícita de
mantenimiento; el generador nunca resuelve paquetes. Las tres variantes Docker
(memoria, Taskiq y combinación con SQLite/AI/auth) prueban instalación y ejecución.
El Core mantiene sus dependencias separadas de estos SDK.

Fuentes: [Taskiq](https://taskiq-python.github.io/guide/architecture-overview.html),
[Taskiq Redis](https://github.com/taskiq-python/taskiq-redis),
[scheduling](https://taskiq-python.github.io/guide/scheduling-tasks.html).

## Observabilidad (fase 10)

| Dependencia | Versión fijada | Alcance |
| --- | --- | --- |
| opentelemetry-sdk | 1.44.0 | Traces, metrics y exportación local del API |
| opentelemetry-exporter-otlp-proto-http | 1.44.0 | Exportación OTLP estándar HTTP/protobuf |
| @opentelemetry/api | 1.9.1 | API de tracing JavaScript |
| @opentelemetry/sdk-trace-base | 2.11.0 | Span CLIENT del helper web |

Los locks opcionales incluyen hashes Python e integridad npm. Se regeneran mediante
`scripts/lock_observability.py`, respetando constraints del resto de integraciones.
El Core no incorpora esos SDK como dependencias propias. Pruebas Docker verifican
la variante base y la composición con SQLite, Redis, AI, auth y Taskiq.
Fuentes: [Python](https://opentelemetry.io/docs/languages/python/instrumentation/) y
[propagación](https://opentelemetry.io/docs/languages/python/propagation/).

## Herramientas de especificación y estándares (fase 11)

OpenSpec `@fission-ai/openspec@1.13.2` usa Node >=20.19.0. Sus dependencias están
fijadas en `src/harness/data/tooling/package-lock.json`; se instalan con `npm ci
--ignore-scripts --no-audit --no-fund`. No se añade una dependencia al runtime
de la aplicación ni al entorno Python del Core.

Agent OS 3.0 está fijado al commit `475b0cac4c7c5cf2336ad5a663b691a6d3415e05`,
que incorpora correcciones posteriores del instalador en macOS. SHA-256 del archivo:
`57363bf71e6b2b457583f8ad6758cabe8cd0643a6223dbcdc4b0c4a6bf6b572f`.
El script oficial se ejecuta sin modificaciones; se activan solo sus tres comandos
de estándares. Los fuentes y la licencia MIT permanecen en el directorio local
de tooling. OpenSpec también usa MIT. Pins centrales: `src/harness/data/tooling/pins.json`.

La instalación fue verificada con Node 24.2.0, npm 11.7.0 y Bash de macOS ARM64.
El estado es experimental y no implica validación de todos los hosts de agentes.
La página pública de instalación de Agent OS actualmente pide acceso por email;
se consultó y utilizó el instalador del repositorio oficial público, sin registros.

Fuentes: [OpenSpec Installation](https://openspec.dev/docs/installation),
[OpenSpec CLI](https://openspec.dev/docs/cli),
[Agent OS installer fijado](https://github.com/buildermethods/agent-os/blob/475b0cac4c7c5cf2336ad5a663b691a6d3415e05/scripts/project-install.sh)
y [Agent OS changelog](https://github.com/buildermethods/agent-os/blob/475b0cac4c7c5cf2336ad5a663b691a6d3415e05/CHANGELOG.md).

## Prototipos y navegador (fase 12)

El frontend del prototipo añade `@playwright/test==1.64.0` (Apache-2.0) a las
dependencias de desarrollo. Sus transitivas y hashes se fijan en el lock de
`src/harness/templates/prototype/apps/web/package-lock.json.tmpl`. El script
`scripts/lock_prototype.py` mantiene este lock a partir del frontend base; no
se ejecuta al generar proyectos. Node 24.2.0 y Chromium descargado por esta
versión de Playwright son la plataforma comprobada.

No se añade un router JS ni un servidor propietario: rutas hash en React,
contratos FastAPI/Pydantic y repositorio de memoria con biblioteca estándar.
Playwright necesita instalar su Chromium por separado; el smoke utiliza una
caché local al workspace bajo `.tools/playwright-1.64.0`.

Fuentes: [Playwright instalación](https://playwright.dev/docs/intro),
[browsers](https://playwright.dev/docs/browsers) y
[test CLI](https://playwright.dev/docs/test-cli). La prueba móvil es emulación
Chromium, no evidencia de Safari/iOS ni de un dispositivo físico.
# Incorporaciones de fase 13

Terraform 1.15.8 es una herramienta externa (licencia BSL 1.1), no dependencia
Python del Core. El proveedor hashicorp/google 8.6.0 (MPL 2.0) queda fijado por
versión y lock con hashes para darwin_arm64 y linux_amd64. `scripts/lock_cloud.py`
actualiza explícitamente esos artefactos; scaffold no descarga proveedores.
El contenedor reutiliza Node 24 y Python 3.12 con imágenes fijadas por digest y
los locks existentes de web/API/telemetría. No se añade ningún SDK cloud al Core.
Consulta `docs/phase-13-report.md` para el alcance real de las comprobaciones.

La ampliación 0.13.1 añade hashicorp/azurerm 5.9.0 (MPL 2.0), descargado y firmado
por HashiCorp, con lock para darwin_arm64/linux_amd64. Se verifica con Terraform
1.15.8 usando validate y planes con proveedor simulado; no se afirma despliegue
Azure probado. `scripts/lock_cloud.py --provider azure` mantiene ese lock.
No se añade SDK Azure al Core ni al contenedor. Ver `phase-13-multicloud-report.md`.
