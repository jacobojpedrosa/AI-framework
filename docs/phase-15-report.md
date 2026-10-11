# Fase 15 — diagnóstico

Versión interna 0.15.0; skeleton 13.0.0. Implementado `harness doctor`
con salida legible o JSON y resultados pass/warn/fail/unverified.

## Alcance

Inspección estática de configuración, estructura y hashes del manifiesto,
marcadores OpenSpec/Agent OS, matriz de compatibilidad, configuración de auth,
AI y telemetría, locks Terraform, workflows CI, sintaxis del backend y coherencia
del manifiesto frontend con el lock. Se buscan algunos patrones de secretos en
archivos del manifiesto; no equivale a una auditoría completa ni del historial Git.

`--runtime` observa exclusivamente endpoints loopback, contratos health/readiness,
HTML y assets referenciados y contenedores del proyecto Compose seleccionado.
Los logs tienen límites de tiempo y tamaño y solo se comunican recuentos de errores.
No se inicia ningún proceso de aplicación, se importa código del proyecto ni se
ejecutan migraciones. No se realizan llamadas cloud ni a proveedores AI.

`--fix` presenta un plan; `--fix --approve` restaura archivos ausentes cuya versión,
configuración y hash permiten reproducir exactamente el original. Se guarda un
registro previo de ausencia y hashes en `.harness/doctor-backups/`. Los archivos
modificados y las plantillas antiguas requieren intervención específica.

Tres skills empaquetadas y generadas en `skills/` guían el diagnóstico de backend,
frontend y navegador. El navegador usa las herramientas existentes del host;
no se incorpora un driver o servicio adicional al framework.

## Evidencia

- 408 pruebas Core en Python 3.14 y Python 3.12; 21 pruebas específicas de doctor.
- Fallos deliberados detectados: YAML inválido, Python inválido, package.json
  inválido, telemetría inválida, despliegue PROD automático y patrón de secreto.
- Pruebas de archivo ausente, preview sin cambios y restauración aprobada;
  archivos modificados y manifiestos antiguos no se sobrescriben.
- Hashes y fechas de modificación verifican el comportamiento de solo lectura.
  Pruebas de symlinks, traversal y direcciones remotas rechazan entradas inseguras.
- Dobles HTTP y Docker demuestran detección de dependencia no disponible, asset
  ausente, contenedor parado y errores de logs sin revelar cuerpos o credenciales.
- Ruff, formato, build offline y smoke del wheel instalado fuera del repositorio
  correctos. Las tres skills pasan `quick_validate.py` de skill-creator.
- Diagnóstico real de `output/phase12-example`: API health/readiness, dependencia,
  web, asset y dos contenedores disponibles. Detectado workflow CI ausente, pues
  ese proyecto precede a fase 14. Resultado: 15 pass, 1 fail, 3 warn, 3 unverified.
  No se actualizó el proyecto ni se modificaron sus datos.
- Herramientas del host: formulario Add feedback visible en la pestaña existente;
  cero avisos/errores capturados (máximo 20). No se envió el formulario. Esta
  observación no demuestra ausencia de todos los errores ni valida flujos completos.

## Límites y siguiente fase

Credenciales válidas, autorizaciones admin reales, migraciones aplicadas, pgvector,
almacenamiento, workers, entrega de telemetría, estado Terraform, infraestructura
DEV y protecciones efectivas de GitHub no se consideran comprobados por una
configuración presente. Se marcan pendientes cuando falta evidencia runtime.
No se consulta el registro remoto de versiones. La inspección de navegador se
realiza mediante la skill y el host, no automáticamente desde la CLI.

Gate 15: demostradas varias categorías de fallos y reparación acotada con aprobación.
La fase 16 (motor de actualización) y la fase 17 (endurecimiento) siguen pendientes.
