# Informe de fase 2 — resolución de golden paths

Fecha: 2026-09-23. Versión interna: 0.2.0. Fase autorizada por el usuario tras
la entrega y revisión de fase 1.

## Resultado

`harness setup` lee decisiones explícitas en YAML o en un bloque `harness-spec`
de Markdown, pregunta solo los datos de arquitectura ausentes y produce una
propuesta determinista de `project.yaml`, con razones y capacidades seleccionadas.
Sin `--write`, no modifica el proyecto.

Las cuatro rutas cuentan con metadatos, reglas de selección y ejemplos con
resultados esperados guardados en el repositorio:

| Entrada | Resultado |
| --- | --- |
| Web, cero servicios | simple-web; sin capas hexagonales por defecto |
| Sin web, un servicio | ai-service |
| Web, un servicio | fullstack-ai |
| Dos o más servicios, con o sin web | service-platform |

Una elección de ruta incompatible con los hechos explícitos se rechaza. Las
desviaciones de layering requieren justificación. Las capacidades opcionales
no se activan automáticamente; sus dependencias se comprueban y las integraciones
siguen en estado planned.

Al usar `--project`, las opciones existentes se conservan salvo cambios explícitos.
La escritura requiere confirmación o `--approve`, comprueba el snapshot, crea
backup exacto y reemplaza el archivo. Una propuesta sin cambios semánticos no
reescribe ni crea copias. No se han añadido dependencias ni cambiado el esquema
de proyecto 1; la especificación de entrada tiene su propio esquema 1.

## Verificación ejecutada

| Comprobación | Resultado |
| --- | --- |
| Suite completa con Python 3.14.6, macOS ARM64 | 138 pruebas superadas |
| Suite completa con Python 3.12.13, macOS ARM64 | 138 pruebas superadas |
| Ruff lint y formato | Correctos |
| Cuatro especificaciones → YAML esperado | Coincidencia exacta |
| Markdown de ejemplo → propuesta JSON | fullstack-ai, solo ai.fake y database.memory seleccionadas |
| Esquemas JSON contra modelos | Coinciden |
| sdist y wheel 0.2.0 | Build correcto |
| Wheel instalado fuera del repositorio | Help, init, validate y setup operativos |
| Actualización desde wheel | Propuesta, backup, escritura y validación correctos |
| Contenido de distribución | Matriz incluida; entornos y cachés excluidos |

Se conservan las pruebas de fase 1 y se añaden 60 casos: tabla de decisión,
conflictos, defaults, razones, entradas incompletas, preguntas interactivas,
aceptación/cancelación, entradas Markdown ambiguas, preservación de configuración,
parches de capacidades, eliminación explícita, no mutación del preview, idempotencia,
symlinks, lock, snapshot obsoleto, edición entre comprobaciones, colisiones de
temporales y fallo de reemplazo con conservación de original y copia.

Comandos utilizados:

```bash
make UV=.tools/bin/uv lint test
UV_PROJECT_ENVIRONMENT=.venv312 UV_CACHE_DIR=.uv-cache .tools/bin/uv run --locked --offline --python /opt/homebrew/bin/python3.12 pytest
UV_CACHE_DIR=.uv-cache .tools/bin/uv build --offline
UV_CACHE_DIR=.uv-cache .tools/bin/uv run --locked --offline python scripts/smoke_wheel.py --uv .tools/bin/uv
UV_CACHE_DIR=.uv-cache .tools/bin/uv run --locked --offline harness setup examples/specifications/product.md --json
```

Toda la instalación y validación de esta fase utilizó las dependencias ya
cacheadas. `uv.lock` solo cambia la versión del paquete interno.

## Archivos nuevos

```text
src/harness/filesystem.py
src/harness/resolution/__init__.py
src/harness/resolution/golden_paths.py
src/harness/resolution/specification.py
src/harness/resolution/resolver.py
src/harness/resolution/setup.py
src/harness/resolution/writer.py
schemas/specification.schema.json
tests/unit/test_resolution.py
tests/unit/test_writer.py
tests/cli/test_setup.py
docs/setup.md
docs/phase-2-report.md
examples/specifications/product.md
examples/specifications/simple-web/spec.yaml
examples/specifications/simple-web/expected-project.yaml
examples/specifications/ai-service/spec.yaml
examples/specifications/ai-service/expected-project.yaml
examples/specifications/fullstack-ai/spec.yaml
examples/specifications/fullstack-ai/expected-project.yaml
examples/specifications/service-platform/spec.yaml
examples/specifications/service-platform/expected-project.yaml
```

## Archivos modificados

```text
.gitignore
README.md
pyproject.toml
uv.lock
src/harness/__init__.py
src/harness/cli.py
src/harness/config/loader.py
scripts/export_schema.py
scripts/smoke_wheel.py
tests/cli/test_cli.py
docs/architecture.md
docs/dependencies.md
docs/implementation-plan.md
```

El esquema `schemas/project.schema.json` se regeneró sin cambios semánticos.
Los artefactos de build y entornos locales están excluidos de Git; no se ha
creado repositorio Git, commit ni publicación.

## Límites y decisiones pendientes

- Texto libre no se convierte en decisiones automáticamente: requiere el bloque
  estructurado o responder a las preguntas. No se incorpora un LLM en Core.
- Se elige una topología; no se generan aplicaciones, contenedores, workers ni
  infraestructura. El objetivo de URL DEV en menos de dos horas sigue pendiente
  de las fases de generación/despliegue.
- Una actualización real normaliza YAML y traslada comentarios/formato originales
  al backup. Sin cambios semánticos se preserva el archivo completo.
- El lock coordina escritores del harness. La comprobación de contenido/inodo
  detecta ediciones antes del reemplazo, pero no elimina la ventana mínima frente
  a un editor externo que escriba exactamente entre comprobación y reemplazo.
- Un cierre abrupto puede dejar locks o temporales. No se borran automáticamente
  locks ajenos. Linux y Python 3.13 no se han ejecutado; Windows sigue sin soporte
  para escritura segura.
- Los schemas describen tipos; las reglas de arquitectura y capacidades también
  necesitan el resolver. Los adaptadores todavía no tienen soporte operativo.

## Gate 2

Demostrada la transformación determinista de entradas en `project.yaml` para las
cuatro rutas, con pruebas y documentación. Se entrega fase 2 y se mantiene la
revisión previa a fase 3: generar el primer proyecto fullstack con web, API,
Docker Compose y Makefile, todavía con servicios de ejemplo.
