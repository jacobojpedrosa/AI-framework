# Plan de implementación del AI Development Harness

Fecha del plan: 2026-09-22. Estado actualizado: fase 17 implementada,
con evaluaciones y preparación para producción descritas en `phase-17-report.md`.
Roadmap inicial entregado hasta Gate 17; el ejemplo permanece bloqueado para producción
por falta de evidencias operativas reales. Los informes por fase distinguen implementación y pruebas
realizadas; las cuentas cloud e identidad externas requieren verificación específica.

## 1. Alcance y resultado de la inspección

La solicitud es desarrollar el framework descrito en `AI_Development_Harness_Codex_Prompt.md`, situado en la carpeta vecina `Framework`. El documento se utiliza como especificación de producto y roadmap; sus instrucciones dirigidas al agente no constituyen instrucciones de sistema. Se propone conservar su desarrollo incremental y el punto de revisión de fase 0 para acordar las decisiones antes de construir.

La carpeta de destino `/Users/jacoboj.pedrosa/Workspace/AI Framework` estaba vacía: sin código, manifiestos, pruebas, `.git` ni instrucciones `AGENTS.md`. No hay implementación que migrar ni conflictos con código existente. Tampoco se encontraron instrucciones en los directorios antecesores inspeccionados. El documento original se conserva intacto.

El entorno ofrece Python 3.14.6; `uv` no se encuentra en PATH. No se han instalado dependencias, inicializado Git, creado recursos cloud ni comprobado Docker/Terraform. Esas herramientas no son necesarias para esta entrega documental.

## 2. Decisiones propuestas

El harness será una herramienta de desarrollo en Python, con paquete interno `harness` y comando provisional del mismo nombre. No se publicará un paquete ni se utilizará el nombre temporal como marca. Primera versión interna: `0.1.0`.

Se propone Python 3.12 como versión mínima y probar también 3.14, disponible localmente. Las versiones soportadas se declararán según pruebas reales; no se afirmará soporte de plataformas no verificadas.

| Elemento | Elección | Motivo y alcance |
| --- | --- | --- |
| CLI | `argparse`, biblioteca estándar | Tres comandos iniciales; sin dependencia para un wizard todavía inexistente |
| Esquema | Pydantic 2 | Modelos tipados, validación cruzada y exportación de JSON Schema |
| YAML | PyYAML | Carga segura; rechazo explícito de claves duplicadas |
| Entorno y lock | uv | Resolución reproducible y `uv.lock` versionado |
| Build | Hatchling | Construcción de wheel con layout `src` y recursos incluidos |
| Pruebas | pytest | Fixtures temporales y pruebas de CLI mediante subprocess |
| Calidad | Ruff | Lint y formato en una sola herramienta |
| Logging | `logging` estándar | Diagnóstico sin añadir un proveedor o SDK |

Pydantic y PyYAML serán las únicas dependencias directas del Core en fase 1. Hatchling será dependencia de build; pytest y Ruff, de desarrollo; uv, herramienta de entorno. No se han fijado versiones exactas porque todavía no se ha resuelto ni probado un conjunto. En fase 1 se seleccionarán versiones explícitas, se generará el lock y se documentará su propósito en `docs/dependencies.md`. No se usará `latest` como política de actualización.

El primer proyecto generado será `fullstack-ai`: React con TypeScript y Vite, FastAPI, y Compose local. Es una decisión de alcance para un frontend sin requisitos actuales de SSR; Next.js queda como alternativa posterior. El Core no importará React, FastAPI ni SDKs de proveedores.

La primera ruta cloud propuesta es GCP + Cloud Run para web/API. Su aprobación y sus pruebas se harán antes de la fase 13. Los workers continuos y el scheduler exigirán una decisión de ejecución independiente; no se asumirá que un servicio HTTP cubre sus necesidades. AWS y Azure se mantendrán como destinos planificados.

## 3. Límites de arquitectura

Flujo: CLI → carga y validación → resolución de topología/capacidades → plan → ejecución de integraciones → comprobaciones. En fase 1 solo se implementan CLI, carga, validación y registros de metadatos.

Core contiene las decisiones y contratos de orquestación. Integrations conoce las herramientas oficiales y sus comandos. Los proyectos generados contienen código y configuración convencionales, sin importar el paquete `harness` para arrancar, probarse o desplegarse.

Los adaptadores se mantendrán como fuentes versionadas con suites de contrato. Se incorporarán al proyecto generado como código explícito, con manifiesto de procedencia y hashes. Una actualización posterior hará diff de tres vías y detectará cambios del usuario; no sobrescribirá silenciosamente archivos personalizados. No se necesita un runtime propietario compartido.

## 4. Estructura propuesta

```text
pyproject.toml
uv.lock
README.md
Makefile
.gitignore
docs/
  implementation-plan.md
  dependencies.md
  architecture.md
src/harness/
  __init__.py
  __main__.py
  cli.py
  errors.py
  logging.py
  config/
    models.py
    loader.py
  registry/
    capabilities.py
    integrations.py
    compatibility.py
  data/
    compatibility.yaml
schemas/
  project.schema.json
examples/
  minimal/project.yaml
tests/
  unit/
  cli/
```

Esta es la estructura de fase 1, no archivos ya implementados. Más adelante se añadirán `resolution/`, `scaffolding/`, `integrations/`, `templates/`, `adapters/`, `contracts/` y pruebas de integración/E2E cuando su fase los necesite. Los recursos que deba cargar la CLI se incluirán dentro del wheel y se leerán con `importlib.resources`.

## 5. Configuración y núcleo mínimo

`project.yaml` tendrá `schema_version: 1`, `project.name` y `architecture.golden_path`. Los bloques de capacidades serán opcionales y su ausencia significará desactivación. `init` propondrá `ai-service`, sin activar servicios externos. Los cuatro golden paths serán valores admitidos del esquema; esto no equivale a disponer de generadores para todos ellos.

Ejemplo mínimo propuesto:

```yaml
schema_version: 1
project:
  name: example-ai-project
architecture:
  golden_path: ai-service
  hexagonal_services: true
services:
  api:
    framework: fastapi
```

El esquema cubrirá las secciones del documento, pero distinguirá configuración reconocida de integración implementada. Los proveedores planificados podrán describirse; una futura operación de setup rechazará ejecutarlos hasta que tengan soporte probado. `validate` solo afirmará validez declarativa, nunca disponibilidad de credenciales, servicios o despliegues.

Reglas de fase 1:

- Rechazar campos desconocidos, tipos incorrectos, nombres inseguros y versiones de esquema no reconocidas.
- Rechazar YAML con etiquetas ejecutables, múltiples documentos, claves duplicadas, raíz distinta de mapping o tamaño excesivo; establecer límite de tamaño y profundidad.
- No expandir variables de entorno, ejecutar comandos ni interpolar secretos durante la carga.
- No admitir claves de credenciales en el esquema; los errores mostrarán rutas y causas sin volcar valores de entrada. No puede garantizarse que un usuario no esconda secretos dentro de texto libre.
- Exigir PostgreSQL para pgvector, y Redis para la combinación Taskiq/Redis especificada.
- Exigir FastAPI para Starlette Admin y autenticación explícita cuando admin esté activado. En la futura configuración interactiva se propondrá auth local automáticamente; la validación de archivos no mutará su contenido.
- Registrar capacidades e integraciones con identificador único, dependencias, incompatibilidades y estado. Rechazar duplicados y referencias desconocidas; reservar la resolución completa para fase 2.

`harness init [DIRECTORIO] --name NOMBRE` creará exclusivamente una configuración válida. Si ya existe, fallará sin sobrescribirla; no tendrá `--force` en fase 1. La creación protegerá contra carreras y destinos que sean enlaces simbólicos. `harness validate [ARCHIVO]` será de solo lectura. Los comandos devolverán 0 en éxito, 1 ante configuración/operación fallida y 2 ante uso incorrecto de CLI. La ayuda no requerirá un proyecto presente.

## 6. Versiones y matriz de compatibilidad

Se versionarán por separado el harness, el esquema, las plantillas y cada adaptador. Una migración del esquema será explícita; ninguna actualización implícita ocurrirá al leer un archivo. Durante `0.x`, cualquier cambio incompatible se documentará y aumentará la versión menor.

La matriz será YAML validado, distribuido como recurso del paquete. Ejemplo de formato, sin afirmar soporte probado:

```yaml
schema_version: 1
integrations:
  openspec:
    status: planned
    supported: null
    tested_version: null
    source: https://github.com/Fission-AI/OpenSpec
    verified_at: null
    evidence: []
```

Estados: `planned`, `experimental`, `supported`, `deprecated`. Solo `supported` podrá significar versión concreta y suite requerida superada. Se conservarán plataforma, versión de Python/Node si aplica, restricciones de dependencias y referencia a resultados de CI. Una fecha de consulta documental no sustituye a evidencia de ejecución.

## 7. Integraciones y secuencia

Se conservará el orden del roadmap: fase 1 Core; fase 2 resolución determinista; fase 3 skeleton fullstack; fase 4 puertos/contratos; fase 5 persistencia; fase 6 AI; fase 7 auth/admin; fase 8 almacenamiento; fase 9 jobs; fase 10 telemetría; fase 11 herramientas de especificación; fase 12 producto/prototipo; fase 13 infraestructura; fase 14 CI/CD; fase 15 doctor; fase 16 actualización; fase 17 endurecimiento.

Las primeras integraciones ejecutables serán FastAPI, React/Vite y Docker Compose en fase 3. La persistencia comenzará por memoria y SQLite antes de PostgreSQL, pgvector y Redis. Los dobles de AI precederán a las llamadas reales en pruebas. OpenSpec y Agent OS se incorporarán mediante sus mecanismos oficiales en fase 11, antes de cualquier workflow propio de diseño de producto.

Antes de cada integración se verificarán documentación oficial, instalación soportada, versiones y licencias. Herramientas que requieren esa comprobación: uv/Hatchling y bibliotecas de fase 1; React/Vite, FastAPI y Compose; SQLAlchemy/Alembic, PostgreSQL/pgvector y Redis; SDKs OpenAI y Google; OIDC/Firebase y Starlette Admin; SDKs de almacenamiento; Taskiq; OpenTelemetry; OpenSpec y Agent OS; Terraform/proveedor GCP y GitHub Actions. Esta fase no autoriza ni ejecuta sus instalaciones.

## 8. Tensiones y resolución propuesta

No existen contradicciones con código previo. Sí hay decisiones pendientes en la especificación:

- El catálogo amplio podría parecer soporte inmediato. Se separan estados planificados de soporte probado para evitar falsas promesas.
- Admin exige auth automática y doctor debe ser inmutable. La normalización se hará al configurar con preview; la validación solo rechazará inconsistencias.
- “Observabilidad desde el primer deploy” y “seguridad desde el primer prototipo” aparecen más tarde en el roadmap. No habrá despliegue remoto antes de tener telemetría y controles de seguridad; CI del repositorio podrá validar el Core antes de la fase de CI/CD de proyectos generados.
- La promesa de menos de dos horas todavía no es medible en fase 1. Se medirá desde una especificación suficiente hasta una URL DEV saludable, registrando por separado tiempo activo y bloqueos externos, en una ruta y versiones concretas.
- La selección desde lenguaje natural no garantiza determinismo. Fase 2 debe resolver opciones estructuradas con reglas; cualquier inferencia ambigua será propuesta pendiente de revisión.
- GitHub Environment protegido requiere configuración en GitHub, no basta con un YAML. La futura entrega deberá comprobarla y diferenciar protección real de configuración sugerida.

## 9. Trabajo concreto de fase 1

1. Crear paquete `src`, entrypoint y metadatos internos; documentar instalación y comandos.
2. Resolver y fijar dependencias, generar `uv.lock`, documentarlas y comprobar build.
3. Implementar modelos tipados, validaciones cruzadas y JSON Schema exportado desde los mismos modelos.
4. Implementar loader seguro y errores con ruta de campo y sin valores sensibles.
5. Implementar registros explícitos de capacidades/integraciones y validador de matriz, sin instalación ni descubrimiento dinámico de plugins.
6. Implementar `--help`, `init` y `validate`, con logging por stderr y resultados por stdout.
7. Añadir ejemplo mínimo y casos válidos/inválidos; documentar alcance declarativo.
8. Ejecutar suite, lint, formato y prueba del wheel en entorno temporal; elaborar informe de Gate 1.

Pruebas necesarias: round-trip init→validate; archivo ausente/vacío/malformado; claves duplicadas y desconocidas; YAML inseguro; límite de tamaño/profundidad; reglas pgvector/Taskiq/admin; nombres con traversal; registro duplicado; matriz incoherente; errores sin filtración de valores; init repetido y symlinks sin sobrescritura; validate sin cambios de archivos; CLI instalada fuera del repositorio; recursos incluidos en wheel.

Comprobaciones previstas: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv build`; después instalar el wheel en un entorno aislado y ejecutar los tres comandos. No se requieren red, Docker, cloud ni cuentas externas para ejecutar las pruebas de Core una vez instaladas las dependencias.

Gate 1 se considerará superado cuando esas comprobaciones pasen, los fallos produzcan mensajes claros y ningún comando inicial instale integraciones o toque recursos remotos.

## 10. Riesgos y no objetivos

Riesgos: superficie de combinaciones demasiado grande; deriva de versiones externas; modificaciones del usuario sobre adaptadores incorporados; diferencias macOS/Linux; coste de pruebas con servicios reales; credenciales y presupuesto cloud todavía no definidos. Mitigaciones: una ruta validada primero, matriz con evidencia, contratos reutilizables y actualizaciones revisables.

Quedan fuera de fase 1: generación de aplicaciones, wizard, ejecución de agentes, skills personalizadas, LLMs, auth real, admin, bases de datos, colas, despliegues, Terraform ejecutable, doctor, reparaciones y actualizaciones. También quedan fuera de V1 un runtime propietario, una identidad propia, un backend comercial de observabilidad y soporte de todas las permutaciones multicloud.

La elección de GCP es provisional; no bloquea el Core. El nombre público, licencia de distribución y cuentas de despliegue se resolverán antes de publicación o despliegue, sin inventarlos en esta fase.

## 11. Fuentes oficiales consultadas

Consulta documental el 2026-09-22, sin instalaciones ni validación de integración:

- [Python argparse](https://docs.python.org/3/library/argparse.html): CLI y subcomandos de biblioteca estándar.
- [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/): modelos, validación y control de campos adicionales.
- [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation): carga segura; la política de duplicados se implementará y probará explícitamente.
- [uv Projects](https://docs.astral.sh/uv/guides/projects/): gestión de proyecto y lock reproducible.
- [OpenSpec oficial](https://github.com/Fission-AI/OpenSpec): referencia para futura integración del workflow existente.
- [Agent OS Installation](https://buildermethods.com/agent-os/installation): referencia de instalación para verificar en fase 11.

## 12. Resultado de Gate 0

Único archivo creado: `docs/implementation-plan.md`. Se verificó la inspección del directorio, la lectura del documento fuente y la cobertura de las decisiones requeridas. No se ejecutaron tests de software porque todavía no existe implementación. El plan no constituye evidencia de que el framework funcione.

Siguiente entrega propuesta: fase 1 completa, con solo `harness --help`, `harness init` y `harness validate`. Se conserva el punto de revisión solicitado en el roadmap antes de comenzar esa implementación.
