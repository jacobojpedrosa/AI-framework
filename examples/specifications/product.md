# Asistente documental

Una aplicación web permite consultar documentos a través de un servicio API.
Esta descripción orienta al equipo; solo el bloque siguiente determina la
propuesta de arquitectura del harness.

```harness-spec
spec_version: 1
name: document-assistant
web: true
services: [api]
capabilities:
  ai:
    providers: [fake]
  database:
    provider: memory
```
