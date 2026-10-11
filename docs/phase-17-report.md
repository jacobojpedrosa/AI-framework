# Fase 17 — evaluaciones AI y preparación para producción

Core 0.17.0; skeleton 14.0.0. Sin nuevas dependencias del Core.

## Entrega

- Runner standalone de evaluaciones por el puerto TextProvider, dataset sintético
  versionado y hook de grader local. CLI con exact match, hashes del dataset,
  modelo/proveedor, latencia y estado por caso; no imprime prompts ni respuestas.
  Máximo 50 casos, 16000 caracteres por prompt y 2048 tokens de salida por caso.
  Los proveedores reales exigen `--live`; no se realizaron llamadas facturables.
- `harness readiness`: inventario de once categorías cuando existe AI, doctor
  estático, validación de formato, fecha con timezone (máximo 30 días) y hash del
  manifiesto. Los datos son atestaciones del operador, no pruebas independientes.
  Ninguna salida autoriza producción automáticamente.
- Guía generada de hardening, restauración, migraciones expand/contract,
  compatibilidad de esquema y rollback por revisión/imagen en GCP y Azure.
  No se ejecutan migraciones, restauraciones ni despliegues desde esta fase.
- Baseline HTTP local con límites, sin redirects, estadísticas p50/p95 y recuento
  de errores. El presupuesto por defecto es ilustrativo, no un SLO de producción.

## Pruebas y Gate 17

430 pruebas Core pasan en Python 3.14 y 3.12; 10 específicas de esta fase.
Incluyen bloqueo por ausencia, caducidad, hash incorrecto o fallo de evidencia,
read-only, eval incorrecto, omisión de prompts y autorización de llamadas reales.
Ruff, formato, build offline y smoke del wheel instalado fuera del repositorio pasan.

`scripts/smoke_hardening.py --output output/phase17-release --python .venv-ai/bin/python`
genera un ejemplo nuevo, ejecuta 69 tests API, dos evals fake y 30 peticiones a una
API temporal. La API se detiene al terminar; no se toca Signal. Los artefactos están
en `output/phase17-release/.harness/verification/`: tests.log, ai-evals.json,
performance.json y production-readiness.json.

La prueba adicional de imágenes con `smoke_ai.py --variant all` no pudo ejecutarse:
el daemon Docker no estaba disponible. Esto queda pendiente; no se presenta como
validación de contenedores. La inclusión del dataset en la etapa development del
Dockerfile se verifica estructuralmente. Los tests API se ejecutaron en el entorno
Python local existente con los SDKs y dobles de transporte.

Gate 17 entrega un [informe de preparación del ejemplo](phase-17-production-readiness.md)
con estado bloqueado y evidencia local explícita, sin afirmar preparación real de PROD.

## Límites

Los evals fake verifican el mecanismo, no calidad, seguridad o coste de un modelo.
Los hooks permiten añadir datasets del dominio y graders; requieren revisión del
equipo del producto. Las recetas operativas son guías, no recuperación automatizada.
El baseline no mide concurrencia, negocio, cloud ni bases de datos. Las atestaciones
pueden quedar obsoletas tras cambios ambientales aunque su fecha/hash sean válidos.
No se auditó una cuenta cloud ni se probaron credenciales o identidades reales.

Documentación oficial consultada el 2026-10-10 para las guías:
[PostgreSQL backup](https://www.postgresql.org/docs/16/backup.html),
[Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html),
[Cloud Run revisions](https://docs.cloud.google.com/run/docs/managing/revisions),
[Azure Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions).
