# Fase 9 — Jobs, workers y scheduler

Fecha: 2026-09-24. Core 0.9.0; plantilla 7.0.0.

## Implementación

- `JobQueuePort` y `SchedulerPort` asíncronos; dominio y casos de uso independientes
  de Taskiq, Redis y FastAPI.
- Registro explícito de handlers y horarios. Ejemplo `heartbeat`, sin efectos externos;
  horario `heartbeat-default` desactivado inicialmente.
- Memoria: cola limitada, consumidor durante el lifespan del API y scheduler por
  intervalos. Se agrupan intervalos perdidos y se retienen los últimos 100 resultados.
- Taskiq 0.12.6 y taskiq-redis 1.2.3: Redis Streams, resultados con TTL de una hora,
  worker separado y proceso scheduler. Los horarios se guardan en un hash Redis con
  nombres registrados y valores limitados a activación e intervalo.
- Redis de jobs usa un volumen AOF independiente de la caché efímera; sin puerto público.
- CLI de desarrollo: `harness jobs list`, `harness jobs run heartbeat` y
  `harness schedules list`. El Core invoca la CLI generada mediante argumentos Docker
  Compose; la aplicación sigue siendo independiente del Harness.
- Recurso Starlette Admin `schedules`, únicamente con registro explícito, sesión,
  permisos de lectura/escritura y CSRF. No admite expresiones, rutas Python ni nuevos
  handlers desde formularios. También rechaza campos adicionales y horarios desconocidos.
- Dependencias opcionales fijadas con hashes y restricciones de los locks anteriores;
  no se añaden SDK de ejecución al Core.

## Evidencia

`scripts/smoke_jobs.py` crea proyectos y volúmenes con nombres únicos, y elimina
solamente esos recursos al terminar. Usa credenciales locales sintéticas.

La prueba en memoria comprueba CLI, login, bloqueo anónimo, CSRF, registro explícito
y modificación de horarios; su servicio generado pasa 24 pruebas. La variante Taskiq
comprueba además consumo por un worker Docker real, un job programado por el scheduler
real y visibilidad compartida de horarios desde admin y CLI; pasa 43 pruebas, incluidos
contratos con Redis real. La variante combinada añade SQLite, los cuatro proveedores AI
y auth local: pasa 111 pruebas y los mismos escenarios de worker/scheduler. Las tres
variantes pasan lint y formato. Las llamadas AI de esa variante usan HTTP simulado.

El Core pasa 280 pruebas en Python 3.12 y Python 3.14; Ruff y formato también pasan.

Las pruebas unitarias incluyen cola llena, fallo del handler, intervalos inválidos,
desactivación de horarios, rechazo de nombres arbitrarios, permisos de solo lectura,
composición determinista y checksums. Los contratos de Taskiq usan también su SDK real
con un transporte en memoria; los resultados Docker constituyen la evidencia de procesos
separados. El smoke de wheel comprueba que los templates y locks están empaquetados y que
los casos de uso se importan sin instalar SDK.

Los logs y resultados de integración están en `output/jobs-verification/`.
El ejemplo declarativo está en `examples/jobs/project.yaml`; cada proyecto generado
incluye `services/api/JOBS.md`.

## Límites

En memoria, estado y horarios pertenecen al proceso del API; una invocación CLI es
otro proceso y muestra los valores registrados por defecto. `jobs run` consume su
job en esa misma invocación. Para worker separado y estado compartido se utiliza Taskiq.

La entrega puede repetirse tras un fallo. Los handlers deben ser idempotentes y hay
que ejecutar una sola réplica del scheduler. Esta fase no implementa liderazgo
distribuido, exactly-once, dead-letter queue, retención automática del stream ni política
de reintentos de negocio. AOF everysec conserva la ventana habitual de pérdida de Redis
de hasta un segundo. Desactivar un horario no cancela jobs ya encolados.

La validación de esta fase no equivale a verificar cuentas cloud o proveedores de
identidad externos de fases anteriores. La integración admin aquí probada usa auth local.

Referencias primarias: [arquitectura de Taskiq](https://taskiq-python.github.io/guide/architecture-overview.html),
[scheduling](https://taskiq-python.github.io/guide/scheduling-tasks.html) y
[adaptador Redis](https://github.com/taskiq-python/taskiq-redis).

Gate 9: encolado, consumo, programación y administración verificados; pausa antes de
la fase 10 de observabilidad.
