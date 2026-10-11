# Fase 16 — actualizaciones revisables

Core 0.16.0; sin nuevas dependencias del Core ni cambios en el runtime generado.

## Implementación

`harness update` compara los hashes del manifiesto original, los archivos actuales
y el bundle fijado que incluye el Harness instalado. Valida configuración, matriz
empaquetada y capacidad de renderizar esa combinación. Rechaza destinos ajenos al
bundle instalado, downgrades desde manifiestos más nuevos, formatos desconocidos,
cambios de configuración y colisiones con cambios del usuario. No es un resolver
de versiones arbitrarias ni una afirmación de compatibilidad de todas las versiones.

El preview incluye rutas, hashes anteriores/posteriores, revisión Git y comandos
de validación. Su SHA-256 es la aprobación exigida para aplicar. El repositorio
debe estar limpio, tener commit inicial y todos los archivos gestionados existentes
versionados. Rutas con traversal o enlaces simbólicos se rechazan.

La aplicación prepara una rama y un worktree nuevos desde la revisión aprobada;
verifica de nuevo los archivos del candidato antes de escribir. El original no se
modifica. Se ejecutan dependencias, tests, contratos, E2E y doctor. Los cuatro
primeros son recetas explícitas del proyecto; no se asume que todos compartan un
runner. Hay límite de diez minutos por paso y se termina su grupo de procesos
local ante timeout; servicios Docker iniciados por una receta requieren su propio
cleanup. Los logs de subprocessos no se publican en el informe.

Se verifica que la validación no haya modificado los archivos gestionados.
El informe deja el estado `ready-for-human-review` únicamente cuando todos los
pasos terminan correctamente. En caso de fallo conserva el candidato y el informe.
No hay commit, merge, push, instalación global, Terraform apply ni despliegue.

## Demostración de Gate 16

`scripts/smoke_update.py --output output/phase16-smoke` crea un repositorio local
de prueba con una referencia sintética anterior de FastAPI en `requirements.in`.
No representa una instalación histórica validada de esa versión: es una fixture
para demostrar la transición de archivos a las dependencias fijadas actuales.

El candidato pasó build Docker, tests del proyecto, contratos y E2E HTTP real:
health/readiness tanto por la API como a través del proxy web, y entrega del HTML.
Los contenedores usan nombre y puertos exclusivos y se eliminan al terminar.
El manifiesto del origen permanece idéntico. Una versión destino `999.0.0` fue
rechazada. Evidencias: `preview.json`, `incompatible.json` y el informe del candidato
en el directorio de salida. Signal y su stack persistente permanecieron intactos.
La repetición final en `output/phase16-final` pasó los cinco pasos y confirmó
`managed_files_unchanged_by_checks: true` con el control de integridad añadido.

La suite cubre además archivos modificados, incompatibilidades de formato y
configuración, symlinks, worktree separado, aprobación inválida, paso fallido,
preservación de cambios ajenos y alteración del candidato durante la validación.

Validación del Core: 420 pruebas pasan en Python 3.14 y 3.12, incluidas 12 del
motor de actualización. Ruff y formato correctos. Build offline y smoke del wheel
0.16.0 instalado fuera del repositorio correctos, incluyendo el subcomando update.

## Límites

Solo se admite el skeleton fullstack, no migraciones de prototipos personalizados.
La comprobación de compatibilidad estructural no sustituye las pruebas del proyecto.
El E2E de la demostración es HTTP, no navegador ni recorrido de producto.
Doctor se ejecuta estáticamente: sus comprobaciones externas pendientes aparecen
en el informe y no se presentan como aprobadas.

Las recetas se ejecutan como código local de confianza, con el entorno heredado;
el worktree aísla archivos del candidato pero no constituye un sandbox de seguridad.
El usuario debe revisar los comandos y su cobertura, sin credenciales en argumentos.
El motor no puede probar que una receta arbitraria tenga tests significativos o
carezca de efectos externos. Las recetas de la demostración son exclusivamente locales.
Revisar y fusionar el candidato exige una acción humana posterior.

La fase 17 (AI evals y endurecimiento) sigue pendiente.
