# Fase 12 — Diseño de producto y prototipo funcional

Fecha: 2026-10-09. Core 0.12.0; renderer de prototipo 1.0.0 sobre skeleton 9.0.0.

## Entrega

`harness project-design` lee una definición YAML tipada y produce documentación,
la definición portable y evidencia de referencias. Detecta únicamente decisiones
ausentes: nombre, propósito, personas, casos de uso, flujos, pantallas, entidades,
integraciones, AI y constraints. `[]` declara ausencia de integraciones o AI;
omisión significa pendiente. Código 2 indica preguntas por resolver. No llama
modelos, interpreta prosa ni escribe código de aplicación durante el diseño.

La skill `src/harness/data/skills/project-design/SKILL.md` conecta el brief y las
herramientas del host con ese contrato. Antes de crearla se revisaron los workflows
instalados de OpenSpec 1.13.2 y Agent OS 3.0: OpenSpec ya aporta exploración, preguntas,
propuesta, diseño, tareas y aplicación; Agent OS aporta estándares. La extensión
propia cubre el formato de entrada del renderer, referencias y entrega al prototipo,
sin generar propuestas paralelas ni sustituir prompts upstream. La skill supera
`quick_validate.py`; se incluye en el paquete y el proyecto generado para uso
explícito, sin instalación global ni ejecución de agentes en estas pruebas.

`harness prototype ... --approve` genera un proyecto nuevo tras revisar la definición.
`--dry-run` es inmutable. Comparte el escritor seguro de scaffold, rechaza colisiones
y rutas peligrosas y conserva un manifest de hashes de todos los archivos iniciales
y del producto. No sobrescribe ni instala dependencias durante la generación.

## Ruta implementada

El ejemplo Signal parte de `examples/product-design/feedback.yaml` y genera:

- React ejecutable con listado, búsqueda, filtro por estado, detalle y formulario.
  Rutas hash permiten recarga y navegación atrás. Vistas de escritorio y móvil,
  labels de formulario, foco visible y estados de carga, vacío, error y validación.
- FastAPI real: GET/POST `/api/items` y GET `/api/items/{id}`; OpenAPI en
  `/api/openapi.json`. Creación responde 201 con Location; errores 404, 422 y 409.
- Dominio y casos de uso independientes de FastAPI, puerto de repositorio y
  adaptador thread-safe de memoria. Seeds sintéticos desde la definición, máximo
  1000 registros, datos aislados por proceso. La UI usa el API sin fallback ficticio.
- Contrato de entrada estricto, campos desconocidos rechazados, límites de texto
  y estados declarados. Cliente TypeScript valida la forma de las respuestas.
- Pruebas API y Playwright 1.64.0, configuración de escritorio/móvil, captura de
  fallos y reportes. El script de smoke levanta web/API Docker reales y usa Chromium
  local. No se añade una dependencia del Harness al runtime generado.

El renderer admite exactamente una entidad con `title`, `description`, `status`
y pantallas `list`, `detail`, `create`. Rechaza otros campos, más entidades, otras
pantallas e integraciones externas/AI, conservando esas necesidades en la definición
de diseño. Esto demuestra una ruta concreta; no constituye generación arbitraria
de productos a partir de lenguaje natural.

## Referencias y diseño

Admite imágenes locales PNG/JPEG/WebP relativas al YAML, con comprobación de firma,
límite de 5 MiB y rechazo de symlinks/traversal. Las copia con SHA-256 y rebasa sus
rutas para que la definición exportada sea portable. La firma no acredita que toda
la imagen sea decodificable. URLs HTTPS se conservan sin descargarlas. La evidencia
queda marcada como pendiente de revisión por el host; no se inventa inspección visual.

El host puede usar herramientas de imagen/diseño para aportar observaciones a
`design.direction`. El renderer aplica contenido, estados y acento; conserva la
dirección visual y constraints en texto sin afirmar que los haya implementado.
El ejemplo usa el layout editorial propio, sin imágenes de referencia externas.

## Verificación del Gate 12

- 342 pruebas Core en Python 3.12 y 3.14; 29 nuevas cubren preguntas parciales,
  integridad y portabilidad de referencias, límites, rechazo de formas no soportadas,
  aprobación explícita, ausencia de sobrescrituras y generación determinista.
- Prototipo: 26 pruebas API, incluidas las reglas de arquitectura hexagonal y el
  contrato real; 3 pruebas del helper health heredado del skeleton.
- 4 E2E Chromium: creación con 201, lectura, recarga, búsqueda/filtro, detalle,
  navegación atrás, ausencia de resultados, item inexistente, formulario inválido
  y recuperación de red. Dos escenarios se ejecutan en escritorio y móvil emulado.
  Solo el caso de error de red intercepta una respuesta 503 deliberadamente.
- Lint, formato, typecheck y build del frontend; lint/formato de API y Core.
- Wheel y sdist construidos; instalación aislada del wheel verifica recursos,
  documentación de producto y generación de prototipo fuera del repositorio.
- Capturas revisadas de escritorio 1440×1000 y móvil 390×844. E2E móvil usa Pixel 7
  emulado; no representa prueba en Safari ni en un dispositivo físico.

Evidencia reproducible: `scripts/smoke_prototype.py --output <directorio nuevo>`.
Ejemplo final: `output/phase12-example`. Logs, capturas y `results.json` están en
su `.harness/verification`. El script retiró únicamente su stack Docker al terminar.
La vista previa local, si está activa, tiene nombre/puertos en `.harness/preview.json`.

Las pruebas iniciales detectaron dos problemas en el E2E: Node necesitaba el atributo
de importación JSON y la espera del error de red aceptaba un aviso anterior. Ambos
se corrigieron y los cuatro recorridos pasan sin reintentos automáticos.

## Límites

Prototipo local, sin autenticación, despliegue público, persistencia durable,
edición/borrado, adjuntos ni funciones AI. Los datos sobreviven a recargas del
navegador y se pierden al reiniciar el API. No se comparten entre workers.
La UI base usa inglés; el contenido del producto puede estar en otro idioma pero
el renderer no traduce todas las etiquetas. No se certifica accesibilidad completa.

No se ejecutó un LLM para evaluar la skill. Se validó su estructura y el flujo CLI
real que documenta. Las referencias externas requieren capacidades del host y
revisión humana/agente, no una integración Figma automática en este Core.

Fuente de E2E: [Playwright](https://playwright.dev/docs/intro) y
[browsers](https://playwright.dev/docs/browsers). Versión fijada y alcance registrado
como experimental en la matriz de compatibilidad.

Gate 12 completado. Pausa antes de fase 13: IaC y abstracción cloud.
