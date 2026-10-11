# Informe de preparación para producción — ejemplo AI

Fecha: 2026-10-10. Proyecto: `output/phase17-release`, generado con Harness 0.17.0.
Configuración: React/FastAPI, puertos hexagonales y proveedores fake/OpenAI/Gemini/Vertex.
Pruebas ejecutadas exclusivamente con fake y dobles de transporte. Sin entorno cloud
desplegado, persistencia duradera ni identidad real configurada en este ejemplo.

**Resultado: BLOQUEADO PARA PRODUCCIÓN.** Se ha validado el mecanismo del framework;
no existe evidencia suficiente de un producto ni de un entorno operativo real.

| Área | Evidencia local | Pendiente para una decisión de producción |
| --- | --- | --- |
| Configuración y estructura | Doctor sin fallos estáticos; manifiesto íntegro | Revisar cambios del producto y configuración efectiva |
| Tests | 69 tests API y 430 tests Core | E2E del producto y matriz de despliegue reales |
| AI | 2/2 casos sintéticos; mecanismo de fallo probado | Dataset del dominio, calidad, seguridad, privacidad, coste y modelos reales |
| Rendimiento | 30 GET locales, 0 errores, p50 0,630 ms, p95 0,907 ms | Carga representativa, concurrencia, recursos, negocio y SLOs en staging |
| Dependencias | Lock y workflow de auditoría presentes | Auditoría actual del artefacto que se desplegará |
| Imágenes | Dataset incluido en etapa development | Repetir build/tests Docker: daemon no disponible en esta comprobación |
| Identidad y secretos | Ninguna credencial real utilizada | Roles, denegaciones, admin, TLS, rotación y restricciones de red |
| Backup y migración | Guía y mecanismos existentes documentados | Elegir persistencia, definir RPO/RTO, ensayar restore y migraciones |
| Rollback | Estrategia por revisión/imagen documentada | Ensayo con schema compatible y verificación posterior |
| Monitorización | Guía de señales y alertas entregada | Entrega real de telemetría, alertas y responsable operativo |
| Aprobación | `production_authorized: false` | Revisión independiente del release, evidencias y entorno |

Los once registros de evidencia operativa están ausentes deliberadamente: no se
fabricaron atestaciones positivas a partir de pruebas locales. El reporte JSON
incluye también avisos por herramientas de desarrollo sin inicializar y proveedores
AI sin credenciales. La ausencia de credenciales es esperada en este ensayo offline.

Evidencia reproducible:

```bash
.venv/bin/python scripts/smoke_hardening.py \
  --output output/otra-verificacion --python .venv-ai/bin/python
harness readiness --project output/otra-verificacion
```

El entorno Python indicado debe contener las dependencias del servicio generado.
La prueba abre solo una API temporal loopback y la detiene al terminar. Los logs y
reportes se conservan bajo `.harness/verification/` del ejemplo. El código 1 de
readiness expresa el bloqueo esperado, no un fallo de generación.

Para continuar hacia producción: concretar un producto y entorno, completar sus
pruebas y ensayos operativos, resolver hallazgos, registrar evidencias fechadas
vinculadas al manifiesto y someter el release a revisión humana. Completar el
roadmap del framework no sustituye ese trabajo por proyecto.
