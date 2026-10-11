# Fase 11 — OpenSpec y Agent OS

Fecha: 2026-09-24. Core 0.11.0; plantilla 9.0.0.

## Entrega

`harness integrations init --project <directorio>` instala e inicializa herramientas
oficiales en un proyecto generado. `--dry-run` muestra pins y destinos sin escrituras,
subprocesos ni red. `scaffold` sigue siendo puro y añade `DEVELOPMENT_TOOLS.md`.

OpenSpec 1.13.2 se instala localmente mediante `npm ci`, con lock de todas sus
dependencias e integridad npm; no ejecuta scripts de lifecycle. Su CLI oficial ejecuta
`init --tools claude,codex --profile core --no-animation`. Instala seis skills para
cada host y seis comandos Claude. No se copian prompts propios que repliquen sus flujos.

Agent OS 3.0 usa el archivo oficial del commit
`475b0cac4c7c5cf2336ad5a663b691a6d3415e05`, incluyendo correcciones del instalador
posteriores a 3.0. Se verifica SHA-256 antes de extraerlo y ejecutar su script oficial
`scripts/project-install.sh --profile default` sin modificaciones. Se rechazan links
y archivos especiales; la extracción también aplica el filtro seguro de tarfile.
El archivo, los fuentes y las licencias se conservan bajo `.harness/tooling/`.

El instalador crea sus cinco comandos originales; el Harness activa únicamente
`discover-standards`, `inject-standards` e `index-standards`, conservando su contenido
exacto. `shape-spec` y `plan-product` quedan solo en los fuentes descargados, fuera de
los comandos activos, para mantener las especificaciones bajo OpenSpec.

El perfil upstream no contiene estándares instalables en esta revisión. Se añade
una norma de propiedad y límites arquitectónicos y su entrada de índice. OpenSpec
la referencia desde su configuración de contexto. No se introducen skills propias.

| Herramienta | Responsabilidad |
| --- | --- |
| Agent OS | Estándares de ingeniería: cómo construimos |
| OpenSpec | Especificaciones y cambios: qué cambia |
| Harness | Configuración, scaffolding y orquestación |

La instalación utiliza staging dentro del proyecto, rutas de estado XDG locales,
telemetría upstream desactivada y un lock exclusivo. Rechaza destinos existentes,
incluidos directorios de hosts con contenido ajeno. Los fallos ordinarios revierten
solo los directorios creados por la invocación. No modifica instalaciones globales,
el perfil del shell, dependencias de la aplicación ni el manifest inicial de scaffold.
Un recibo independiente registra versiones, commit, runtime y hashes de archivos
instalados; estos hashes son evidencia inicial, no impiden editar estándares después.

## Verificación

- 313 pruebas del Core en Python 3.12 y 3.14; 27 nuevas prueban instalación, preview,
  protección de destinos y symlinks, locks, checksum, extracción, reversión y errores.
- Ruff: lint y formato del Core y scripts.
- Build de wheel/sdist y smoke de instalación aislada sin red. Incluye locks/pins
  empaquetados y preview de integraciones; excluye `node_modules` de la distribución.
- Instalación real en macOS ARM64 con Node 24.2.0, npm 11.7.0 y Bash del sistema.
- `scripts/smoke_integrations.py`: ejecuta CLI oficial para crear un cambio de prueba,
  obtener instrucciones con contexto de Agent OS, validar estrictamente, comprobar
  estado completo, archivar y validar estrictamente la especificación creada.
- Verificación de hashes del recibo, skills instaladas para Claude/Codex y comparación
  byte a byte de los tres comandos Agent OS con el commit descargado.

Ejemplo verificado: `output/phase11-release/`. Evidencia detallada:
`.harness/integrations.json` y `.harness/integration-smoke.json` dentro del ejemplo.
El cambio de prueba queda archivado y no afecta al runtime de la aplicación.
La matriz registra ambas integraciones como experimentales con versiones exactas.

Reproducción, con salida nueva y acceso a npm/GitHub:

```bash
uv run --locked python scripts/smoke_integrations.py --output output/integrations-check
```

## Límites

No se ejecutaron modelos ni sesiones interactivas de Claude o Codex. Se verificaron
el CLI real, los instaladores y los archivos oficiales. Agent OS publica comandos
Claude, no skills nativas Codex en este commit; Codex recibe las skills oficiales
OpenSpec y sus referencias a los estándares. No se promete compatibilidad de todos
los hosts o versiones de Node: la ejecución real corresponde a macOS ARM64/Node 24.

La operación cubre instalaciones nuevas, no actualización, restauración ni fusión
de archivos existentes. El código descargado está aislado como dependencia de
desarrollo, sin fork mantenido por el Harness. Un corte abrupto puede dejar lock,
staging o publicación parcial: requieren inspección antes de reintentar. No deben
editarse destinos durante la instalación. La actualización segura corresponde a
una fase posterior; no se llama automáticamente a `latest` ni a `openspec update`.

La prueba inicial de archivado detectó que OpenSpec genera un Purpose provisional
si el delta omite esa sección. El fixture final declara Purpose y pasa validación
estricta tanto antes como después del archivo.

Fuentes oficiales consultadas: [OpenSpec instalación](https://openspec.dev/docs/installation),
[CLI](https://openspec.dev/docs/cli),
[Agent OS instalación](https://buildermethods.com/agent-os/installation) y
[fuentes fijados de Agent OS](https://github.com/buildermethods/agent-os/tree/475b0cac4c7c5cf2336ad5a663b691a6d3415e05).
La página de Agent OS requiere acceso por email; se utilizó el instalador del
repositorio público oficial, sin registrar al usuario.

Gate 11 completado. Pausa antes de la fase 12: diseño de producto y prototipo funcional.
