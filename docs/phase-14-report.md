# Fase 14 — CI/CD por entorno

Core 0.14.0; skeleton 12.0.0. Gate 14: lógica y permisos de workflows.

## Entrega

El scaffold genera GitHub Actions para validación en PR y pushes a develop/main:
lint, pruebas API/contratos y web, builds, baseline de secretos rastreados,
pip-audit y npm audit. Los proyectos cloud añaden fmt, validate y pruebas Terraform.
Local no genera despliegues; GCP/Azure incluyen DEV opcional y PROD manual.

DEV solo puede desplegar desde un push a develop después de validar y activar
DEV_DEPLOY_ENABLED. PROD solo desde workflow_dispatch en main, con digest revisado
y PROD_DEPLOY_ENABLED. Ambos flags están desactivados por omisión. No hay
pull_request_target, permisos globales de escritura ni claves cloud estáticas.
Las acciones tienen SHA inmutable y checkout no persiste credenciales.

Solo los jobs de despliegue/publicación reciben id-token:write. El guard de PROD
consulta la protección real del Environment antes de autenticar: revisores,
prevención de autoaprobación, sin bypass administrativo y política exclusiva main.
Falta de token lector, permisos o protección bloquea la operación. La generación
no crea ni configura esos controles en GitHub.

DEV publica la imagen del commit validado y obtiene su digest del registro. PROD
usa un digest ya publicado en su registro; promoción/copia queda como operación
externa revisada. Los comandos solo actualizan servicios existentes y verifican
su etiqueta de entorno antes de modificar. Se comprueba imagen/revisión nueva,
tráfico GCP y HTTP health/readiness. No hay rollback automático ni canary.

Azure mantiene ingress interno y Single revision. La publicación DEV usa un runner
hospedado con Docker; el despliegue usa un runner aislado dentro del mismo entorno
Container Apps, sin necesidad de Docker. GCP usa runner hospedado y health con
identity token. No se abre ingress para facilitar pruebas.

Terraform conserva infraestructura y CI/CD administra la imagen después del
provisioning: ignore_changes afecta solamente al campo image. Bootstrap, cambios
de infraestructura y estado conservan plan/review/apply manual; no se incorpora
apply automático. PROD requiere infraestructura propia revisada, estados e
identidades separados; no reutiliza automáticamente las plantillas DEV.

## Validación realizada

- 387 pruebas Core en Python 3.12.13 y 3.14.6, incluyendo 16 casos de CI/CD:
  eventos permitidos, aislamiento de permisos, bloqueo de PROD sin protección,
  digest obligatorio, revisión nueva y contratos de health/readiness.
- Actionlint 1.7.12 valida los cinco workflows de local/GCP/Azure. Binario oficial
  con checksum verificado. Shellcheck y pyflakes externos desactivados; helpers
  Python comprobados con Ruff y pruebas del Core.
- Regresión Terraform GCP: fmt, validate, planes offline y cuatro tests correctos.
  Azure: fmt, validate y cuatro planes con proveedor simulado correctos.
- Contenedores GCP/Azure linux/amd64 ejecutados localmente con health/readiness,
  assets y telemetría correctos. Sin creación de recursos cloud.
- API del ejemplo: 22 pruebas. Web: lint, cinco pruebas y build correctos.
- pip-audit del ejemplo stateless: sin vulnerabilidades conocidas en esa consulta.
  npm audit detectó una vulnerabilidad alta en source-map-js 1.2.1; se actualizó
  únicamente ese paquete a 1.2.2 en los locks base, observabilidad y prototipo.
  El audit web repetido devolvió cero vulnerabilidades. No se afirma que todos
  los proveedores opcionales o futuras bases de advisories estén libres de hallazgos.

Evidencias de workflows: `output/phase14-workflows-release/results.json`.
Terraform/contenedores: `output/phase14-gcp-verified` y `output/phase14-azure-verified`;
la repetición GCP con el lock corregido está en `output/phase14-cloud-release`.
Los scripts reproducibles son `scripts/smoke_cicd.py` y `scripts/smoke_cloud.py`.

## Límites y siguiente fase

Gate 14 local satisfecho. No se ha publicado el repositorio, configurado un GitHub
Environment, lanzado Actions remotamente ni probado OIDC/despliegue en cuentas reales.
La operación remota queda pendiente de repositorio, infraestructura y permisos
autorizados. El archivo generado CI_CD.md documenta los requisitos exactos.
La fase 15 (doctor y diagnóstico) no se inicia en esta entrega; después quedan
actualizaciones y endurecimiento.

Fuentes: [GitHub Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers),
[Google auth](https://github.com/google-github-actions/auth),
[Azure login](https://github.com/Azure/login),
[corrección source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
