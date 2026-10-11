# Informe de fase 3 — skeleton fullstack-ai

Fecha: 2026-09-23. Versión interna: 0.3.0. Fase autorizada por el usuario tras
el Gate 2.

## Entrega

`harness scaffold PROJECT.yaml --output DIRECTORIO` genera un proyecto standalone
de 29 archivos a partir de la configuración `fullstack-ai`. Incluye:

- React 19 + TypeScript 7 + Vite 8 en `apps/web`.
- FastAPI 0.141 + Uvicorn 0.53 en `services/api`.
- `compose.yaml` con healthchecks, dependencia web→API, puertos ligados a
  `127.0.0.1`, `init` y `no-new-privileges`.
- Dockerfiles con imágenes oficiales por digest: Node 24 y Python 3.12.
- `Makefile` con `up`, `down`, procesos separados, logs, tests, lint, formato y build.
- `project.yaml`, `.env.example`, `.gitignore` y `.harness/scaffold.json` con
  versión de plantilla y hashes SHA-256.
- Endpoint real `/api/health`, OpenAPI en `/api/openapi.json` y UI web que lo
  consume mediante el proxy same-origin `/api`.

No se generan database, auth, admin, AI, storage, workers, scheduler, cloud ni
IaC. Si aparecen habilitados en la configuración, el comando falla antes de
crear el directorio. Las capacidades permanecen explícitas para una fase futura.
El proyecto resultante no importa el paquete `harness` para ejecutar, probarse o
construirse.

## Verificación

| Comprobación | Resultado |
| --- | --- |
| Suite del harness, Python 3.14.6 | 156 pruebas superadas |
| Ruff lint y formato del harness | Correctos |
| Cuatro golden paths de fases anteriores | Sin cambios; resultados deterministas |
| npm test del frontend generado | 3 pruebas superadas |
| npm run build del frontend generado | Vite 8 compiló el bundle |
| npm run lint del frontend generado | TypeScript y Prettier correctos |
| Docker Compose build | Imágenes API y web construidas |
| Compose `up --wait` | Ambos contenedores healthy durante la ejecución |
| Fuentes oficiales consultadas | Vite, React, FastAPI y Compose |

El build de Compose descargó las imágenes oficiales y los requisitos con hashes.
En la sesión original, la revisión automática de uso de herramientas bloqueó la
verificación posterior. No había evidencia de que Docker se hubiese apagado:
al retomar la tarea los dos contenedores seguían activos. Se corrige aquí esa
afirmación del informe original. El 2026-09-23 se completaron `make test lint build`
en Compose (3 tests API y 3 tests web), una petición HTTP a `/api/health` mediante
el proxy web y `make down`, que eliminó ambos contenedores y su red.

## Archivos principales nuevos

```text
src/harness/scaffolding/fullstack.py
src/harness/templates/fullstack_ai/
tests/unit/test_scaffolding.py
tests/cli/test_scaffold.py
docs/phase-3-report.md
```

La versión del Core pasa a 0.3.0 y el lock se actualizó. El output generado de
verificación está en `output/fullstack-demo`, ignorado por Git; un usuario puede
regenerarlo con:

```bash
uv run --locked harness scaffold examples/specifications/fullstack-ai/expected-project.yaml \
  --output ./fullstack-demo
```

## Límites y riesgos

- El frontend usa Vite como servidor de desarrollo, no como servidor de producción.
- La plantilla copia código en la imagen; hay que reconstruir tras cambios.
- Los Dockerfiles requieren acceso a Docker Hub/PyPI/npm en el primer build.
- El healthcheck web comprueba que Vite responda; el comportamiento de negocio aún
  no existe.
- El proyecto no tiene migraciones, persistencia ni contratos de dominio. La fase 4
  añadirá la plantilla hexagonal y pruebas de contratos.
- Docker Compose fue verificado en Docker Desktop Linux/arm64 local. No se afirma
  compatibilidad de otros motores o plataformas sin pruebas.
- La seguridad de desarrollo limita puertos a localhost y evita privilegios nuevos;
  no equivale a un baseline de producción.

## Gate 3

El proyecto fullstack-ai se genera de forma convencional, tiene `make up` y
`make down`, web/API navegables, tests y healthchecks. Se mantiene la revisión
antes de fase 4: introducir `domain`, `application`, `ports`, `adapters` e
`infrastructure` en el servicio FastAPI y un arnés de pruebas de contratos.
