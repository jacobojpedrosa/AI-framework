# Informe de fase 6 — proveedores AI

Fecha: 2026-09-23. Core 0.6.0; plantilla 4.0.0. Fase autorizada tras Gate 5.

## Entrega y alcance de validación

Se implementan OpenAI, Gemini Developer API, Vertex AI y un adaptador fake bajo
el mismo puerto `TextProvider`. `GenerateText` recibe el puerto por inyección;
cambiar de proveedor no cambia el dominio ni el caso de uso. La composición
elige únicamente proveedores habilitados y no hace fallback implícito a fake.

**Los SDK oficiales y sus contratos se verificaron con HTTP simulado. No se
realizaron llamadas de generación ni validaciones de cuentas reales.** No había
claves OpenAI/Gemini ni configuración explícita de Vertex en las variables
comprobadas. No se buscaron credenciales en archivos personales. El código para
checks remotos y generación real está disponible como operación explícita.

El catálogo marca estas integraciones como experimentales y la matriz conserva
esa limitación. No se afirma compatibilidad de un modelo concreto ni disponibilidad
de cuentas, cuotas o permisos.

## Diseño

- OpenAI: SDK oficial y Responses API, `store=False` y límite explícito de salida.
- Gemini: Google Gen AI SDK en modo Developer API con clave explícita.
- Vertex: el mismo SDK en modo Vertex, proyecto/localización y Google ADC.
- Fake: respuesta constante, sin red ni eco de información privada.

Modelos, claves y contexto cloud se configuran por entorno. El modelo real no
tiene un default inventado. Los clientes se crean solo al ejecutar una operación,
con timeout HTTP y sin retries automáticos, y se cierran al finalizar.

El contrato contempla texto no streaming, límites de entrada/salida y errores
estables. Los adaptadores traducen fallos de autenticación, límites, timeout,
indisponibilidad y respuestas bloqueadas/vacías/incompletas. No pasan excepciones
SDK sin sanitizar al dominio. El CLI devuelve códigos públicos y suprime logs
durante la operación; las claves y el prompt no aparecen en repr de configuración
y petición. No se crea un endpoint HTTP público de generación.

Readiness incluye `ai_configuration`, que **solo comprueba configuración local**.
No consulta credenciales, ADC, modelos ni facturación. Un check remoto distinto
consulta metadatos del modelo; eso no equivale a comprobar permisos de generación.

## Uso

```bash
uv run --locked harness scaffold examples/ai/project.yaml --output ./ai-demo
cd ai-demo
make up
make ai-check
printf 'Entrada de prueba' | make ai-generate
make test-contracts
make down
```

El ejemplo habilita los cuatro proveedores y arranca con fake. Para cambiar,
configurar `AI_PROVIDER` y las variables indicadas en `services/api/AI.md`:
OPENAI_API_KEY/OPENAI_MODEL; GEMINI_API_KEY/GEMINI_MODEL; o VERTEX_MODEL con
GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION y ADC.

`make ai-check-remote` ejecuta una comprobación remota explícita de metadatos.
`make ai-generate-live` permite una generación real con posible coste; sin ese
opt-in el CLI rechaza generar contra un proveedor real. El texto entra por stdin.
No se monta automáticamente ningún archivo de credenciales del host.

El ejemplo final está en `output/phase6-example` (64 archivos); su configuración
reproducible está en `examples/ai/project.yaml`.

## Verificación

| Comprobación | Resultado |
| --- | --- |
| Core, Python 3.14.6 | 263 tests superados |
| Core, Python 3.12.13 | 263 tests superados |
| 15 subconjuntos de proveedores × 6 conjuntos de dependencias | 90 combinaciones verificadas: artefactos opcionales, compilación, determinismo y hashes |
| Dominio/caso de uso y fake con Python -S | Funcionan sin SDK ni site-packages |
| Servicio AI con cuatro proveedores | 67 tests superados |
| Contratos AI compartidos | 34 casos con SDKs reales y transportes HTTP simulados |
| AI + PostgreSQL/pgvector/Redis: tests API locales | 99 superados; 22 contratos externos de persistencia omitidos sin sus variables |
| AI + persistencia: contratos de integración | 92 superados, cero omitidos; DB/cache reales locales y AI simulado |
| Frontend | 3 tests, lint y build correctos |
| Core y proyectos generados | Ruff lint/formato correctos |
| Wheel/sdist 0.6.0 | Construidos; wheel instalado y probado fuera del repositorio |

Se comprueban requests Responses/generateContent, routing de Vertex, límites de
salida, ausencia de retries, metadatos por GET, errores 401/403/429/500/404,
timeout, bloqueo, truncación, texto vacío y sanitización. Las pruebas de runtime
verifican argumentos del cliente y cambio de proveedor a través del mismo caso
de uso. Un test comprueba que el CLI no filtra mensajes privados ni siquiera si
un logger SDK intenta activar DEBUG. Otro impide llamadas SDK en el check local.

`scripts/smoke_ai.py` verificó seis proyectos aislados en Docker: fake, OpenAI,
Gemini, Vertex, todos y todos con persistencia. Los proveedores reales sin
configuración arrancan la API pero reportan readiness no disponible; fake arranca
listo. Cada proyecto termina eliminando sus contenedores/red/volúmenes temporales.
Los logs y resultados están en `output/ai-verification/`.

```bash
uv run --locked python scripts/smoke_ai.py
```

Durante la comprobación se corrigieron dos problemas detectados: imports opcionales
clasificados de forma distinta por Ruff en la variante fake, y un token de prueba
Vertex anónimo que el SDK intentaba refrescar. La plantilla fija los paquetes
locales para isort y los tests Vertex usan un token OAuth sintético explícito.

## Dependencias y límites

SDKs fijados: openai 3.19.0 y google-genai 2.25.0. Se resolvieron 18 locks
runtime/dev para combinarlos con SQL/Redis; fake no añade dependencias. El Core
no instala ni importa estos SDKs. Pruebas Docker en Linux/arm64, Python 3.12.14,
con Docker Desktop/Compose del entorno documentado en fases previas.

El contrato no cubre streaming, embeddings, herramientas, agentes, multimodalidad
ni evaluaciones de calidad. Solo acepta IDs de modelo simples; no endpoints
personalizados. Los límites de tokens no garantizan coste ni éxito de cada modelo.
La resolución/renovación de ADC sigue Google Auth y no está cubierta por un
deadline global de la operación. Las pruebas locales no sustituyen checks live
con credenciales del propietario del proyecto.

Fuentes oficiales consultadas mediante OpenAI Docs y documentación de Google:
[SDK OpenAI](https://developers.openai.com/api/docs/libraries) y
[Google Gen AI SDK](https://googleapis.github.io/python-genai/).

## Gate 6

Se demuestra el cambio fake/OpenAI/Gemini/Vertex sin cambios de dominio mediante
contratos ejecutables contra los SDK. La verificación live queda explícitamente
pendiente de configurar credenciales y modelos. La fase 7 (auth/admin) espera
el siguiente punto de revisión.
