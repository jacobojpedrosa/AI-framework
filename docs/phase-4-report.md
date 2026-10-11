# Informe de fase 4 — servicio hexagonal y contratos

Fecha: 2026-09-23. Core 0.4.0; plantilla 2.0.0. Fase autorizada tras Gate 3.

## Entrega

`harness scaffold` genera 48 archivos para `fullstack-ai` con
`architecture.hexagonal_services: true`. La variante `false` conserva los 29
archivos del skeleton simple. No se amplía aún la generación a otros golden paths.

El servicio contiene `domain`, `application`, `ports`, `adapters` e
`infrastructure`. El ejemplo operativo es readiness, sin dominio de negocio
inventado: `CheckReadiness` recibe sondas y un reloj UTC mediante Protocols.
`ProcessProbe` y `SystemClock` son adaptadores concretos; `create_app` conecta
HTTP con el caso de uso y permite inyección explícita en tests.

`/api/health` mantiene su respuesta compatible. `/api/readiness` devuelve 200
si todas las sondas pasan y 503 si alguna falla. Excepciones o valores distintos
de `True` no informan disponibilidad; los errores privados no se exponen en HTTP.
La sonda por defecto solo comprueba el proceso, no dependencias externas.

Las pruebas de contratos comparten aserciones entre adaptadores reales y fakes.
Incluyen detección de una sonda que devuelve texto y un reloj sin zona horaria.
Se ejecutan con `make test-contracts` y dentro de `make test`. Los tests del
servicio guardan las fronteras de importación mediante AST. El Core prueba
además el caso de uso con `python -S`, sin FastAPI ni otros site-packages.

## Verificación

| Comprobación | Resultado |
| --- | --- |
| Core en Python 3.14.6 | 159 tests superados |
| Core en Python 3.12.13 | 159 tests superados |
| Ruff lint y formato del Core | Correctos |
| Wheel y sdist 0.4.0 | Construidos sin red |
| Wheel instalado fuera del repositorio | CLI, recursos y generación hexagonal verificados |
| API generada, Python 3.12.14 en Docker | 17 tests superados |
| Contratos seleccionados por separado | 7 tests superados |
| Frontend generado | 3 tests, TypeScript, Prettier y build correctos |
| Arranque Compose con espera de salud | API y web saludables |
| HTTP directo y mediante proxy web | Health y readiness correctos |
| Limpieza Docker | Contenedores y red de pruebas eliminados |

Plataforma comprobada: Docker Desktop 4.74.0, Engine 29.4.3, Compose 5.1.4,
Linux/arm64. Las versiones FastAPI 0.141.1 y React 19.3.0 quedan registradas
como experimentales en la matriz, con alcance restringido al skeleton.

Reproducir desde el entorno instalado del harness, con Docker activo:

```bash
python scripts/smoke_scaffold.py
```

El script genera un proyecto temporal, ejecuta arranque, tests, lint, build,
contratos y HTTP, y ejecuta `make down` en un bloque `finally`. Usa un nombre
Compose único; los puertos 15173/18080 deben estar libres o cambiarse con
`--web-port` / `--api-port`. No toca otros proyectos Docker.

## Límites

- Las pruebas de frontera controlan imports estáticos; no son un sandbox Python.
- Los adaptadores con I/O futuro deberán fijar timeouts; este ejemplo síncrono
  no implementa cancelación, retries ni verificación de servicios externos.
- Hay un aviso de deprecación de TestClient por httpx; no hay fallos de tests.
- Continúan pendientes persistencia, AI, auth y las siguientes fases del roadmap.
- No se ha validado producción ni plataformas distintas de la indicada.

Se corrigió el informe de fase 3: el cierre de Docker no estaba demostrado en
la sesión anterior. Al retomar se completaron las comprobaciones pendientes y
se eliminaron los contenedores de aquella ejecución.

## Gate 4

Servicio ejecutable, capas internas independientes y contratos funcionales
demostrados. La fase 5 (persistencia) queda pendiente de aprobación.
