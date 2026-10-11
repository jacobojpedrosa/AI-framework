# Informe de fase 1 — Core mínimo

Fecha: 2026-09-22. Fase 1 autorizada por el usuario tras Gate 0.

## Entrega

Paquete interno `development-harness-internal` 0.1.0 con `harness --help`,
`harness init` y `harness validate`. Implementa configuración tipada, JSON Schema,
carga YAML limitada, errores sin valores de entrada, registros de capacidades e
integraciones y una matriz de compatibilidad distribuida dentro del wheel.

`init` no sobrescribe archivos, valida antes de escribir y protege destinos con
symlinks y escrituras concurrentes. `validate` comprueba reglas declarativas y
no modifica el proyecto. Los 25 identificadores de integración permanecen
`planned`; no se ha activado un servicio cloud, runtime ni adaptador externo.

## Comprobaciones

| Comprobación | Resultado |
| --- | --- |
| pytest, Python 3.14.6, macOS ARM64 | 78 pruebas superadas |
| pytest, Python 3.12.13, macOS ARM64 | 78 pruebas superadas |
| Ruff lint y formato | Correctos |
| uv build: sdist y wheel | Construidos correctamente |
| Instalación del wheel fuera del repositorio | Help, init y validate correctos |
| Recursos instalados | Matriz cargada desde site-packages |
| Archivos de distribución | Sin entornos, cachés ni archivos .env |
| JSON Schema | Coincide con la exportación del modelo |

La suite incluye entradas YAML maliciosas, duplicados, profundidad/tamaño/nodos,
valores escalares inválidos, campos secretos desconocidos, reglas de admin/auth,
Taskiq/Redis y pgvector, errores de permisos, symlinks, carreras de init y
preservación del archivo al validar. Los casos de uso de CLI se ejecutan en
directorios temporales.

Comandos reproducibles en este workspace:

```bash
make UV=.tools/bin/uv lint test
UV_PROJECT_ENVIRONMENT=.venv312 UV_CACHE_DIR=.uv-cache .tools/bin/uv run --locked --offline --python /opt/homebrew/bin/python3.12 pytest
UV_CACHE_DIR=.uv-cache .tools/bin/uv build
UV_CACHE_DIR=.uv-cache .tools/bin/uv run --locked --offline python scripts/smoke_wheel.py --uv .tools/bin/uv
```

Las instalaciones iniciales necesitaron acceso a PyPI autorizado. Las pruebas y
el smoke test del wheel no necesitan red con las dependencias ya en caché. uv
puede consultar el índice al crear su entorno de build; se puede utilizar
`uv build --offline` si su backend ya está cacheado. El aviso de uv sobre caché
dentro del árbol fuente se contrastó inspeccionando los archivos de distribución:
la selección explícita de build excluye ese contenido.

## Límites y riesgos pendientes

- Probado en macOS ARM64, Python 3.12 y 3.14. Linux y Python 3.13 aún no se han
  ejecutado; Windows no está soportado por `init`.
- El esquema cubre opciones futuras sin certificar implementaciones. JSON Schema
  describe la estructura; las reglas entre secciones requieren la CLI.
- No hay código de generación, conexión a proveedores ni despliegues. Tampoco se
  ha medido el KPI de especificación a URL DEV.
- La matriz verifica que existan campos de evidencia al declarar soporte; la
  autenticidad de esa evidencia sigue requiriendo revisión y pruebas reales.
- La versión del backend de build está fijada; sus dependencias transitivas se
  resuelven en un entorno separado del lock runtime/desarrollo.
- No se ha creado repositorio Git, commit ni publicación. El nombre y la licencia
  de distribución continúan pendientes antes de una publicación pública.

## Archivos entregados

Nuevos: `pyproject.toml`, `uv.lock`, `.gitignore`, `Makefile`, `README.md`;
`docs/architecture.md`, `docs/dependencies.md`, este informe;
`examples/minimal/project.yaml`, `examples/fullstack/project.yaml`;
`schemas/project.schema.json`; `scripts/export_schema.py`, `scripts/smoke_wheel.py`.

Código nuevo:

```text
src/harness/__init__.py
src/harness/__main__.py
src/harness/cli.py
src/harness/errors.py
src/harness/logging.py
src/harness/config/__init__.py
src/harness/config/models.py
src/harness/config/loader.py
src/harness/registry/__init__.py
src/harness/registry/base.py
src/harness/registry/capabilities.py
src/harness/registry/integrations.py
src/harness/registry/compatibility.py
src/harness/data/__init__.py
src/harness/data/compatibility.yaml
tests/conftest.py
tests/unit/test_config.py
tests/unit/test_registry.py
tests/cli/test_cli.py
```

Actualizado: `docs/implementation-plan.md`, para registrar aprobación de fase 0.
Artefactos locales excluidos de Git: `.tools`, `.venv`, `.venv312`, `.uv-cache`,
cachés de pruebas/formato y `dist` con el wheel y sdist.

## Gate 1

Los criterios de Core están cumplidos. Se mantiene el punto de revisión del
roadmap antes de fase 2: resolver golden paths y producir decisiones de
arquitectura deterministas, todavía sin generar aplicaciones completas.
