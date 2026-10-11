# Arquitectura del Core y servicios generados

La fase 14 añade `harness.cicd`: workflows declarativos por proveedor y scripts
standalone sin importar el Core. La validación de PR se ejecuta en runners hospedados
con contents:read; solamente los jobs de despliegue reciben id-token:write y un
GitHub Environment. PROD exige evento manual, main y verificación de protección
antes de autenticar en cloud. Los valores externos se pasan por variables de
entorno y argumentos de subprocess, sin interpolarlos como comandos shell.
Terraform conserva la configuración y CI/CD asume la imagen tras provisioning,
mediante ignore_changes limitado al atributo image. No hay applies automáticos.

La fase 10 incorpora `scaffolding.observability`: añade middleware HTTP, providers y
exportadores OpenTelemetry en infraestructura, más un helper de tracing web. Los
SDK no entran en dominio ni aplicación. El bootstrap compone el lifespan existente
para cerrar exporters al apagar sin interferir con recursos o jobs. Logs y métricas
no usan URLs completas ni payloads como atributos. Ver `phase-10-report.md`.

`cli` delega en `config` para leer/validar y contiene la escritura exclusiva de
`init`. `config.models` es la fuente del JSON Schema. `config.loader` aplica
límites antes de construir objetos y sanitiza errores. El parser no interpreta
variables ni importa objetos especificados en YAML.

En la fase 9, `harness.jobs` proporciona el puente de desarrollo hacia una aplicación
generada en Docker Compose. Valida el proyecto y los nombres, invoca una lista fija de
argumentos sin shell y propaga el resultado. El servicio no importa el Core.
`scaffolding.jobs` añade puertos, registro explícito, runtime en memoria o Taskiq,
worker/scheduler y el recurso admin `schedules` únicamente cuando está seleccionado.
Los casos de uso dependen de `JobQueuePort` y `SchedulerPort`; los adaptadores son los
únicos módulos que conocen Redis y Taskiq. La memoria es local al proceso; Taskiq
comparte la cola y horarios mediante Redis persistente. Ver `phase-9-report.md`.

`registry` describe capacidades, herramientas y compatibilidad. Los registros
usan identificadores únicos, referencias comprobadas y requisitos sin ciclos.
Las dependencias se describen sin ejecutar instalaciones.
El catálogo se obtiene mediante `default_capabilities()` y `default_integrations()`;
`load_compatibility()` lee el recurso incluido en el wheel con `importlib.resources`.
No se publica un comando adicional de catálogo en esta fase.

La matriz debe cubrir exactamente las herramientas del registro y coincidir con
su estado. Marcar `supported` exige versión exacta, fecha ISO, plataforma y
referencias a evidencia. Esa validación comprueba la estructura de la evidencia,
no certifica su autenticidad: la promoción de soporte debe revisarse junto con
las pruebas correspondientes. Las integraciones del skeleton y de persistencia
verificadas están en estado `experimental`; las restantes siguen `planned`.

El loader y `init` no instancian SDKs de terceros ni escriben en Git. `init`
recorre directorios usando descriptores y `O_NOFOLLOW`, y crea el archivo con
`O_EXCL` para impedir sobreescrituras y seguimiento de symlinks. Puede crear
directorios padres; si un error posterior impide crear el archivo, esos
directorios vacíos pueden permanecer. No se promete protección frente a un
proceso hostil con permisos para renombrar el árbol completo del usuario.

`resolution.specification` acepta decisiones explícitas del usuario en YAML o
Markdown delimitado. `resolution.golden_paths` contiene metadatos inmutables de
las cuatro rutas. `resolution.resolver` es puro: toma especificación y configuración
existente opcional, detecta datos ausentes, selecciona topología, conserva opciones,
valida las capacidades seleccionadas y devuelve una propuesta con razones.

`resolution.setup` gestiona preguntas, preview, diff y aprobación. `resolution.writer`
realiza solo escrituras locales de configuración; no migra código ni dependencias.
`filesystem` comparte el recorrido POSIX seguro entre init y setup.

La precedencia es: campos explícitos de la especificación, datos del proyecto
existente, valores derivados de una ruta explícita y defaults documentados.
Los datos contradictorios se rechazan; no se resuelven adivinando intención.
Las capacidades omitidas se conservan, las nuevas requieren selección explícita,
y las dependencias faltantes se informan sin instalarlas silenciosamente.

Actualizar requiere el snapshot revisado, un lock exclusivo entre escritores
del harness, copia original y reemplazo con `os.replace` después de una segunda
comprobación. Los editores externos no respetan ese lock: queda una ventana mínima
entre comprobación y reemplazo. No se ofrece compare-and-swap universal ni defensa
frente a procesos hostiles con los permisos del usuario. Una interrupción abrupta
puede dejar un lock/temporal; se debe comprobar que no haya ejecución activa antes
de retirarlo. Las copias originales se conservan incluso si falla el reemplazo.

Los futuros generadores/integraciones consumirán modelos de Core; el Core no
importará sus runtimes. Los proyectos generados no dependerán de este paquete.

`scaffolding.fullstack` es un renderer puro de plantillas empaquetadas. Solo
acepta `fullstack-ai` con una web React y un API FastAPI; rechaza capacidades que
aún no tienen plantilla ejecutable. Genera un proyecto autónomo con provenance
`.harness/scaffold.json`, sin importación del harness en runtime. La escritura
es exclusiva en un directorio nuevo; `--dry-run` solo enumera archivos.

Con `hexagonal_services: true`, el renderer aplica la plantilla empaquetada
`hexagonal_api` sobre el skeleton compartido. Esta superposición interna solo
reemplaza el entrypoint de la API; añade capas, tests y documentación. Con `false`
se conserva la API simple. El manifiesto registra la variante y hashes finales.
No se modifican proyectos existentes.

La aplicación generada usa `CheckReadiness` con puertos `Probe` y `Clock` basados
en Protocol. Dominio, puertos y aplicación solo importan biblioteca estándar y
capas internas permitidas. FastAPI vive en el adaptador HTTP y la composición;
el punto de entrada delega en `create_app`. Los tests del Core importan el caso
de uso con `python -S`, sin site-packages, y ejecutan los contratos generados.
El servicio incluye además una comprobación AST de fronteras de importación.

`scaffolding.persistence` compone overlays opcionales: infraestructura compartida,
repositorio, SQL, vector y caché. Selecciona locks previamente resueltos; renderizar
no invoca pip, uv, Docker ni una base de datos. Los tests verifican las diez
combinaciones de configuración (incluida la ausencia de persistencia).

El repositorio de referencia trabaja con `Record` inmutable; el puerto no importa
SQLAlchemy. Un adaptador SQL comparte operaciones parametrizadas entre SQLite y
PostgreSQL; el driver y la URL cambian en la composición. El puerto vectorial y
el de caché son independientes. `Resources` centraliza construcción y cierre;
sus probes participan en readiness. El lifespan de FastAPI cierra las conexiones.

Las migraciones Alembic están en el proyecto generado, incluidas en la imagen
runtime. El entrypoint de migración toma DATABASE_URL del entorno y aplica head
explícitamente. Una migración posterior activa pgvector solo en PostgreSQL.
Ningún endpoint HTTP ejecuta migraciones ni expone CRUD sin autenticación.

`scaffolding.ai` añade un puerto de generación textual y adaptadores fake/OpenAI/
Google. Gemini y Vertex comparten el adaptador Google con clientes configurados
explícitamente para APIs diferentes. El caso de uso no sabe qué proveedor recibe.
`RuntimeAI` lee configuración validada al ejecutar y usa una sesión que cierra
cliente/transporte. No se crean clientes al importar módulos ni en readiness.

El probe `ai_configuration` solo comprueba campos locales. La consulta remota de
metadatos y la generación real son operaciones explícitas de CLI; esta última
requiere `--live`. Los errores SDK se normalizan antes de cruzar el puerto y el
CLI suprime logs mientras ejecuta diagnósticos. No se crea un endpoint AI público.
Los SDK se incluyen únicamente cuando se seleccionan sus proveedores y se fijan
junto con las capacidades SQL/Redis mediante locks precompilados.

Versiones separadas: paquete `0.6.0`, plantilla `4.0.0`, esquema de proyecto `1`, esquema de
especificación `1`, matriz `1`. El esquema de proyecto no ha cambiado en fase 2.
No se realizan migraciones al validar.
# Infraestructura incorporada en fase 13

`harness.infrastructure` valida una ruta DEV stateless y produce metadatos tipados
independientes del proveedor. El overlay cloud incorpora Terraform convencional
y un entrypoint que sirve React compilado y FastAPI en el mismo origen.
El proyecto generado no importa el Core. Bootstrap (registro y APIs) y servicio
(cuenta de ejecución, Cloud Run e invocadores explícitos) tienen estados separados.
El renderer Azure se incorpora en 0.13.1 mediante un overlay separado; AWS y las
cargas cloud con persistencia o workers siguen pendientes.
La generación no ejecuta Terraform ni utiliza la cuenta cloud activa del host.

`environments.select_environment` aplica una selección explícita local/GCP/Azure
sobre una copia de la configuración y valida sus límites antes de escribir.
Omitir la selección en setup conserva la configuración existente; escoger local
retira cloud/IaC, conservando capacidades de aplicación. Las selecciones que
contradicen bloques explícitos de la especificación se rechazan. La selección
no migra estados Terraform ni sobrescribe código generado.

El overlay cloud comparte Dockerfile y entrypoint web/API. Cada proveedor aporta
solo su infraestructura y README. El metadata distingue IAM de GCP frente al
ingress interno Azure, y memoria 512 MiB frente a 2 GiB con 1 CPU respectivamente.
Se evita presentar diferencias de plataforma como si fueran comportamiento idéntico.
