# Especificación y selección de golden paths

`harness setup [SPEC]` produce una propuesta revisable de `project.yaml`.
No instala herramientas, no genera servicios y no interpreta instrucciones del
texto libre. Toda la operación de selección funciona offline.

## Entrada mínima

```yaml
spec_version: 1
name: assistant-web
web: true
services: [api]
```

`services` enumera procesos API independientes, no entidades, endpoints ni módulos.
`[]` significa explícitamente que no hay servicio independiente; omitir el campo
significa que todavía no se conoce la decisión. Lo mismo ocurre con `web: false`
frente a la ausencia de `web`.

Si faltan `name`, `web` o `services`, el modo interactivo solo pregunta los
ausentes. `--non-interactive` o stdin sin TTY devuelven código 1 y la lista de
campos, sin esperar entrada. `--json` añade `status: incomplete` y `missing`.
No se toman respuestas de pipes: utiliza una especificación estructurada.

| Campo | Tipo / función |
| --- | --- |
| `spec_version` | Entero 1; valor por defecto 1 |
| `name` | Nombre seguro de proyecto, igual que `project.name` |
| `environment` | `local`, `gcp`, `azure`; `aws` está pendiente y se rechaza al seleccionar |
| `web` | Booleano: necesita aplicación web |
| `services` | Lista de nombres únicos, máximo 32 en la especificación |
| `golden_path` | Selección explícita opcional entre las cuatro rutas |
| `web_framework` | `react` o `next`; React por defecto en una web nueva |
| `hexagonal_services` | Booleano opcional; false en simple-web, true en las demás |
| `rationale` | Explicación requerida para una elección de layering distinta del default |
| `capabilities` | Bloques database, cache, ai, storage, auth, admin, jobs, scheduler, observability, cloud, iac |

La especificación tiene su propio JSON Schema en
`schemas/specification.schema.json`; las reglas cruzadas las comprueba el resolver.

## Reglas de decisión

Primero se evalúa el número de servicios: dos o más seleccionan service-platform.
Con uno, web distingue fullstack-ai de ai-service. Con cero, web selecciona
simple-web; cero servicios y ninguna web es un error.

Una ruta explícita aporta datos solo donde no hay elecciones conocidas:
simple-web → web y cero servicios; ai-service → sin web y un servicio `api`;
fullstack-ai → web y `api`. Service-platform no inventa nombres de servicios ni
decide si necesita web: solicita esos datos si faltan. Una ruta explícita que
contradiga web/services se rechaza.

Las capas hexagonales existentes se conservan cuando no cambia la topología.
Al cambiar de ruta se propone el default de la nueva ruta, salvo elección
explícita. Una desviación explícita requiere `rationale`, que aparece en el
informe; la escritura exige aprobación como cualquier propuesta. La justificación
permanece en la especificación o en el informe JSON, sin alterar el esquema del
proyecto para almacenar textos de conversación.

## Entorno de despliegue

`harness init configuracion --name demo --environment azure` prepara una
configuración fullstack generable. Las opciones disponibles son local, GCP y
Azure; AWS permanece pendiente. Sin `--environment`, init conserva el modo
mínimo histórico. No se despliega ni se autentica en ningún proveedor.

En setup, `environment` puede venir del YAML o de `--environment`. Una contradicción
entre ambos o con capacidades explícitas se rechaza. El wizard pregunta por el
entorno en proyectos nuevos cuando no esté definido; en modo no interactivo la
omisión conserva el comportamiento anterior. Al actualizar un proyecto, la omisión
conserva el proveedor y `local` retira solo cloud/IaC, manteniendo observabilidad.

GCP/Azure requieren la ruta fullstack React/FastAPI stateless y capas hexagonales;
la selección añade Terraform y OpenTelemetry si faltan. No cambia silenciosamente
la topología elegida ni elimina capacidades incompatibles para conseguir un plan.
Azure empieza con ingress interno al entorno de Container Apps, sin login de
usuario ni URL pública para el navegador; GCP usa IAM. AWS no se acepta como una
opción ejecutable. `--write --approve` aplica el diff de configuración revisado;
el cambio de proveedor no migra recursos, estados Terraform ni datos existentes.

Las razones se derivan de reglas estables y el YAML se ordena por claves. No hay
fechas ni valores aleatorios en las propuestas. La lista de servicios se trata
como un conjunto de nombres; cambiar su orden no altera el resultado.

## Markdown

Se admite exactamente un bloque de nivel superior marcado `harness-spec`, con
cercas de backticks o tildes. Por ejemplo:

````markdown
# Asistente documental
Los usuarios necesitan consultar sus documentos.

```harness-spec
spec_version: 1
name: document-assistant
web: true
services: [api]
capabilities:
  ai:
    providers: [fake]
```
````

El resto del documento es contexto humano: no se ejecuta y no se extraen
decisiones mediante coincidencias de palabras. Un Markdown sin bloque produce
un error explicativo; se puede añadir el bloque o ejecutar setup sin archivo.
Bloques múltiples, ambiguos o incompletos se rechazan. El mismo loader limitado
de fase 1 se aplica al YAML, sin aliases ni etiquetas ejecutables.

## Capacidades y proyectos existentes

```yaml
# cambios.yaml
spec_version: 1
capabilities:
  database:
    provider: postgres
    vector: pgvector
  cache:
    provider: redis
  jobs:
    enabled: true
    adapter: taskiq
    broker: redis
```

Con `--project project.yaml`, nombre, web, servicios y capacidades se recuperan
del archivo existente y solo se cambian las opciones indicadas. Los bloques se
combinan recursivamente, conservando campos omitidos. Cada bloque de la
especificación debe ser válido por sí mismo: los que requieren `provider` deben
incluirlo. Los bloques sin campos obligatorios, como admin, admiten parches
parciales (`resources`, por ejemplo).

Un bloque `null` elimina una capacidad. Un campo opcional `null` elimina esa
opción dentro del bloque. Si al cambiar PostgreSQL por SQLite existía pgvector,
es necesario indicar también `vector: null`; no se borran dependencias por
suposición. Quitar auth con admin activo, o Redis con Taskiq activo, falla.

No se habilitan capacidades por aparecer en el catálogo. La propuesta enumera
las seleccionadas y verifica referencias/requisitos/conflictos del registro.
Todos sus adaptadores siguen en estado planned. `validate` mantiene el contrato
de esquema de fase 1; `setup` añade la resolución de topología al crear propuestas.

## Preview y escritura

Por defecto no se escribe ningún archivo. YAML va a stdout; explicación, destino
y diff van a stderr. `--json` emite configuración, razones, capacidades, destino
y diff como un objeto. `status: proposed` describe el informe; el código de salida
y stderr indican el resultado de una escritura posterior.

`--write` pide aprobación en terminal. `--write --approve` permite automatización
con aprobación explícita. `--approve` solo nunca escribe y se rechaza.

Sin `--project`, el destino debe ser nuevo. Con `--project`, el destino por
defecto es ese archivo; se puede usar `--output otro/project.yaml` para guardar
una copia actualizada sin modificar la fuente. Un destino diferente que ya
exista no se sobrescribe.

Una actualización en el mismo archivo conserva una copia exacta con nombre
`project.yaml.backup-*`, comprueba el snapshot antes de sustituir y usa reemplazo
atómico. Si no hay cambios semánticos, no reescribe ni crea backup. Una actualización
real normaliza formato/orden y elimina comentarios de la versión nueva; el
backup conserva los bytes originales. No edites el archivo simultáneamente con
la confirmación de escritura: el lock coordina escritores del harness, no los
editores externos. Las limitaciones de concurrencia están en `architecture.md`.

## Ejemplos verificables

Cada carpeta en `examples/specifications/` incluye `spec.yaml` y
`expected-project.yaml` para una ruta. La suite compara el resultado exacto
contra esos archivos; no genera los resultados esperados durante el test.

```bash
uv run --locked harness setup examples/specifications/simple-web/spec.yaml
uv run --locked harness setup examples/specifications/ai-service/spec.yaml
uv run --locked harness setup examples/specifications/fullstack-ai/spec.yaml
uv run --locked harness setup examples/specifications/service-platform/spec.yaml
```
