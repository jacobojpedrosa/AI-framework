# Fase 10 — Observabilidad

Fecha: 2026-09-24. Core 0.10.0; plantilla 8.0.0.

## Implementación

La selección `observability.provider: opentelemetry` añade instrumentación explícita
al cliente web de health y al API. Se mantienen liveness/readiness. La aplicación
generada no depende del Core y no requiere una cuenta comercial.

- Span CLIENT web y contexto W3C `traceparent` por el proxy Vite hacia un span SERVER
  del API. Providers locales a cada runtime evitan cambios al proveedor global.
- Logs JSON con correlación, método, plantilla de ruta, status y duración. Los logs
  de runtime conservan nivel/logger y tipo de excepción; omiten mensajes arbitrarios,
  cuerpos, queries, credenciales y tracebacks. No se captura baggage ni vendor tracestate.
- Contador de peticiones e histograma de latencia en segundos, con buckets HTTP y
  etiquetas acotadas; paths desconocidos usan `unmatched`. Los trace IDs pueden aparecer
  como exemplars, no como etiquetas.
- Exportadores `console`, `otlp` HTTP/protobuf y `none` en el servidor. Spans por lotes,
  métricas cada 30 segundos y vaciado al apagar. Cabeceras OTLP privadas solo en backend.
- SDK Python 1.44.0, API JS 1.9.1 y SDK JS 2.11.0 fijados con hashes/integridad.

## Evidencia del Gate 10

`scripts/smoke_observability.py` levanta proyectos Docker temporales y ejecuta el helper
real del frontend en Node a través del proxy Vite y del API real. Compara el `trace_id`
de CLIENT/SERVER y verifica que `parent_id` del servidor sea el ID del span web.
Comprueba también el request log correlacionado, exportación de métricas al cerrar,
tests, lint y build del frontend. Retira solo sus proyectos y volúmenes temporales.

La variante base ejecuta 21 pruebas API y 5 frontend. La variante combinada incluye
SQLite, Redis, AI, auth, admin, Taskiq y scheduler y activa contratos Redis reales.
Esta variante combinada pasa 115 pruebas API y 5 frontend; ambas variantes pasan
lint, comprobación de tipos y build. El Core pasa 286 pruebas en Python 3.12 y 3.14.
Las llamadas AI son simuladas y la autenticación usada en tests es local.

Los tests OTLP utilizan SDK reales para serializar y decodificar protobuf de trazas
y métricas con una sesión HTTP simulada; no validan cuentas o collectors remotos.
El cruce web/API sí usa HTTP real entre procesos Docker. No es un E2E visual de navegador.
El Core comprueba composición determinista, exclusión de secretos del frontend,
selección opcional, locks y checksums; el smoke del wheel verifica recursos empaquetados.

Evidencia: `output/observability-verification/base-trace.json`, `combined-trace.json`,
`results.json` y logs en la misma carpeta. Ejemplo: `examples/observability/project.yaml`.

## Límites

El baseline instrumenta web → API; no instrumenta SQL, AI o API → worker automáticamente.
Los spans web son salida local de consola, sin envío a collectors. El ratio de muestreo
aplica a raíces nuevas del API; se respeta al padre remoto y el helper web muestrea todo.

`none` desactiva exports del API y mantiene IDs/logs. El middleware externo de errores
de FastAPI puede responder a fallos no controlados sin cabeceras de correlación; el log
conserva los IDs. Las aplicaciones pueden extender el formatter con campos de negocio
revisados y explícitos. No se incluyen retención, alertas, dashboards ni garantía de
entrega de telemetría. La disponibilidad del collector no modifica readiness.

Fuentes: [instrumentación Python](https://opentelemetry.io/docs/languages/python/instrumentation/),
[propagación](https://opentelemetry.io/docs/languages/python/propagation/) y
[contexto W3C](https://opentelemetry.io/docs/concepts/context-propagation/).

Pausa en Gate 10 antes de OpenSpec y Agent OS (fase 11).
