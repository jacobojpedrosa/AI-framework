# Fase 13 — Infraestructura DEV

Fecha: 2026-10-10. Core 0.13.0; skeleton 10.0.0; esquema de infraestructura 1.

## Entrega

El scaffold incorpora una ruta React/FastAPI stateless para GCP Cloud Run con
Terraform convencional. `examples/cloud/project.yaml` selecciona explícitamente
GCP, Terraform, arquitectura hexagonal y OpenTelemetry. La generación no ejecuta
comandos cloud ni lee la selección de proyecto de gcloud.

`infra/workload.json` y su JSON Schema describen componentes, recursos, puertos,
probes y acceso independientemente del proveedor. AWS ECS y Azure Container Apps
siguen planificados. El renderer rechaza persistencia, caché, almacenamiento, AI,
auth/admin de aplicación, jobs y scheduler; no presenta esas capacidades como
servicios cloud implementados.

Dos raíces Terraform separan bootstrap (APIs y Artifact Registry) del servicio
(cuenta de ejecución sin roles de proyecto, Cloud Run y posibles invocadores).
La imagen debe pertenecer al repositorio esperado y usar digest SHA-256. IAM está
activado, no se añaden miembros públicos y se exige autorización de invocación.
Se configuran probes, escalado 0–2, 1 CPU y 512 MiB; no son un límite de gasto.
La eliminación queda protegida y documentada. El backend GCS es una plantilla
opcional; el estado local es el predeterminado para DEV aislado.

El Dockerfile compila React y sirve web/API en el mismo origen. La imagen final
linux/amd64 ejecuta Python como usuario no root y respeta PORT. Usa dependencias
fijadas e imágenes por digest; excluye secretos, estado Terraform y archivos del
host. La telemetría exporta a consola, sin afirmar integración nativa con Cloud
Trace ni desplegar un collector.

## Verificación ejecutada

- 359 pruebas del Core en Python 3.12.13 y 359 en Python 3.14.6; Ruff correcto.
- 22 pruebas de la API generada, con TELEMETRY_EXPORTER=none en la suite; Ruff
  y formato correctos. El contenedor se prueba por separado con exportación real
  a consola. El entorno local de pruebas necesitó instalar click/uvicorn fijados.
- Terraform 1.15.8 y hashicorp/google 8.6.0: fmt, init con lock readonly y validate
  en ambas raíces. Locks oficiales para darwin_arm64 y linux_amd64.
- Plan real del proveedor, con estado vacío, proyecto ficticio, token inválido,
  refresh desactivado y proxy HTTP inaccesible: 4 recursos bootstrap y 2 servicio.
  Los planes sintéticos se eliminan; no se ejecuta apply.
- Cuatro pruebas Terraform con proveedor simulado: servicio privado y acotado,
  invocador autenticado, rechazo de acceso público y de imágenes por tag mutable.
- Build y ejecución real linux/amd64 en Docker Desktop: usuario app, raíz de
  archivos de solo lectura, sin capabilities, PORT=8091 y puerto local dinámico.
  Health, readiness, OpenAPI, HTML compilado, JS/CSS y logs con trace_id correctos.
  Parada y eliminación del contenedor temporal completadas.
- Wheel instalado fuera del repositorio: CLI y generación de cloud verificadas,
  incluidas plantillas, documentación y lock. Sin dependencias cloud en el Core.

Evidencia reproducible: `output/phase13-example/.harness/cloud-verification/results.json`
y logs adyacentes. Ejecutar `scripts/smoke_cloud.py` con un directorio nuevo y
Terraform 1.15.8; `scripts/lock_cloud.py` es mantenimiento explícito de locks.

## Gate 13 y límites

Gate 13 local satisfecho: fmt, validate y plan pasan para el ejemplo generado.
El estado sigue siendo experimental. No se han creado recursos cloud ni datos en
una base de datos. No se ha usado el proyecto GCP preexistente del equipo.
Un despliegue DEV real queda pendiente de un proyecto desechable autorizado y
credenciales; los planes offline no verifican IAM real, cuotas, políticas de
organización, facturación ni disponibilidad de la imagen en el registro remoto.

La fase 14 (CI/CD) no forma parte de esta entrega. Quedan las fases 14–17:
CI/CD, doctor, actualización y endurecimiento.

Referencias: [contrato de contenedor Cloud Run](https://cloud.google.com/run/docs/container-contract),
[despliegue](https://cloud.google.com/run/docs/deploying),
[proveedor Google 8.6.0](https://registry.terraform.io/providers/hashicorp/google/8.6.0/docs/resources/cloud_run_v2_service),
[plan de Terraform](https://developer.hashicorp.com/terraform/cli/commands/plan).
