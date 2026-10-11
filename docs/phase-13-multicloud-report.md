# Fase 13 — Selección de entorno y Azure

Core 0.13.1; plantilla fullstack 11.0.0. Ampliación previa a CI/CD.

## Resultado

`harness init --name demo --environment local|gcp|azure` prepara una configuración
fullstack generable. Sin la opción conserva el init mínimo anterior. Setup acepta
la misma opción y el campo environment de la especificación; pregunta por el
entorno en proyectos nuevos interactivos. La omisión conserva el proveedor existente.
AWS se muestra como pendiente y su selección ejecutable se rechaza.

Las selecciones contradictorias o capacidades cloud no soportadas fallan antes
de escribir. El cambio a local retira cloud/IaC, sin eliminar capacidades de la
aplicación. Cambiar proveedor no migra estados, datos ni recursos desplegados.

Azure añade dos raíces Terraform: bootstrap (grupo de recursos, ACR, identidad,
rol AcrPull limitado al registro y entorno Consumption) y servicio Container Apps.
Usa AzureRM 5.9.0 y Terraform 1.15.8, con hashes oficiales para darwin_arm64 y
linux_amd64. No añade SDKs Azure al Core ni al contenedor. La suscripción y tenant
son explícitos y la autorregistración de proveedores está desactivada.

Ambos proveedores comparten el código web/API y Dockerfile. Los metadatos reflejan
las diferencias: Azure usa ingress interno al entorno y 1 CPU/2 GiB; GCP usa IAM
y 1 CPU/512 MiB. El acceso interno Azure no equivale a autenticación de usuario:
no se ofrece todavía URL pública de navegador ni login Entra ID. ACR desactiva
credenciales de administrador; la imagen se fija por digest del registro previsto.
La documentación explica despliegue, estado remoto opcional, permisos y limpieza.

## Verificación

- 371 pruebas del Core pasan en Python 3.12.13 y 3.14.6; Ruff y formato correctos.
- Se comprueban selección inicial, preview inmutable, cambio con backup, vuelta a
  local, rechazo de AWS y conflictos, aislamiento de plantillas por proveedor,
  hashes de manifiesto y conservación exacta del código de aplicación.
- Azure: fmt, validate y cuatro pruebas de planes con proveedor simulado pasan.
  Se comprueban ingress interno, recursos, identidad, rechazo de tags y registros
  ajenos. No se ha ejecutado un plan AzureRM autenticado ni un despliegue real.
- GCP: regresión de fmt, validate, planes offline con proveedor real y cuatro
  pruebas Terraform correctas.
- Contenedores de ambos ejemplos construidos y ejecutados localmente en
  linux/amd64: usuario no root, raíz de solo lectura, PORT configurable, health,
  readiness, OpenAPI, assets compilados y logs de telemetría correctos. Los
  contenedores temporales fueron eliminados.

Evidencias: `output/phase13-azure-example/.harness/cloud-verification` y
`output/phase13-gcp-multicloud/.harness/cloud-verification`.
El ejemplo `output/phase13-azure-final` incorpora la corrección posterior que
incluye el README específico Azure; sus archivos Terraform y de aplicación son
idénticos a los del ejemplo verificado. La regresión del Core comprueba también
esa documentación. Una repetición adicional del smoke fue bloqueada por un límite
de uso del servicio de aprobación automática; no se ejecutó.

No se han creado recursos cloud ni usado cuentas o suscripciones del equipo.
La verificación de despliegues reales sigue pendiente de entornos autorizados.
La fase 14 (CI/CD por proveedor) queda fuera de esta ampliación.

Referencias: [ingress Azure](https://learn.microsoft.com/azure/container-apps/ingress),
[identidades para imágenes](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull),
[AzureRM 5.9.0](https://registry.terraform.io/providers/hashicorp/azurerm/5.9.0/docs).
