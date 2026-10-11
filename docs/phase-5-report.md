# Informe de fase 5 — persistencia y caché

Fecha: 2026-09-23. Core 0.5.0, plantilla 3.0.0. Fase autorizada tras Gate 4.

## Entrega

El generador `fullstack-ai` acepta capacidades opcionales de persistencia cuando
`hexagonal_services` está activado:

- Repositorio en memoria, SQLite y PostgreSQL con el mismo puerto y contratos.
- pgvector con puerto independiente para upsert, borrado y búsqueda exacta L2.
- Redis con puerto de caché de bytes, namespace y caducidad obligatoria.
- Migraciones Alembic para SQL y una revisión adicional para pgvector.
- Composición de recursos y cierre en el lifespan; readiness prueba las
  capacidades seleccionadas sin ejecutar migraciones.

El ejemplo es un registro clave/valor inmutable, no un dominio de negocio
inventado. SQLAlchemy comparte consultas parametrizadas entre SQLite y
PostgreSQL; los puertos y el dominio no dependen de SQLAlchemy, Redis ni del
harness. La aplicación no expone endpoints CRUD públicos.

El generador copia locks con hashes y añade solo dependencias seleccionadas.
Memoria no añade paquetes. Las variantes sin persistencia conservan su forma
anterior. Las capacidades pendientes (AI, auth, storage, etc.) siguen siendo
rechazadas por scaffold si se solicitan antes de su implementación.

## Uso y operación

```bash
uv run --locked harness scaffold examples/persistence/project.yaml --output ./datos-demo
cd datos-demo
make migrate
make up
make test
make test-integration
make down
```

La variante completa genera 76 archivos. Incluye instrucciones en
`services/api/PERSISTENCE.md`, archivos Alembic convencionales y nuevos targets
`migrate` y `test-integration`. El ejemplo revisable está en
`output/phase5-example`; el input está versionable en `examples/persistence/project.yaml`.

Las migraciones son explícitas e idempotentes al aplicar head repetidamente.
PostgreSQL serializa estos comandos mediante un advisory lock de transacción.
Antes de migrar, health responde y readiness marca la base como no disponible.
`make down` conserva los volúmenes SQL; los procesos DB/cache no publican puertos
al host. Redis usa almacenamiento temporal y no persiste la caché.

Las credenciales incluidas en Compose son defaults desechables de desarrollo.
Las conexiones externas se configuran por entorno; no se guardan secretos reales
en `project.yaml`. No se provisionan servicios cloud.

## Verificación

| Comprobación | Resultado |
| --- | --- |
| Core Python 3.14.6 | 171 tests superados |
| Core Python 3.12.13 | 171 tests superados |
| Lint y formato Core | Correctos |
| Diez combinaciones de configuración, incluida ninguna capacidad | Generación determinista, imports compilables, hashes y dependencias opcionales comprobados |
| Wheel 0.5.0 instalado fuera del repositorio | Genera skeleton y variante de persistencia; puertos importables sin site-packages |
| Variante completa: tests API locales | 49 superados, 22 contratos externos omitidos al no pasar variables de integración |
| Variante completa: contratos con PostgreSQL/pgvector/Redis reales | 58 superados, cero omitidos |
| Frontend de la variante completa | 3 tests, TypeScript, Prettier y build correctos |
| Alembic revision | Nueva revisión creada en un contenedor desechable |

La suite de 58 contratos incluye 24 ejecuciones de repositorio (8 tests compartidos
por memoria, SQLite y PostgreSQL), 12 de vectores (referencia y pgvector), 15 de
caché (fake, Redis y aislamiento) y los 7 contratos de probes/reloj previos.

`scripts/smoke_persistence.py` comprueba las nueve variantes operativas:
memoria, SQLite, PostgreSQL, pgvector, Redis y las cuatro combinaciones de base
de datos con Redis. Genera proyectos temporales con nombres Compose únicos y
puertos locales 15173/18080. Para cada variante comprueba arranque, readiness
directo y por proxy, tests API, contratos externos seleccionados y lint/formato.
En SQL verifica además doble upgrade, conservación de registros tras down/up,
downgrade a base y nuevo upgrade. Solo sus bases desechables reciben el downgrade.
Un bloque `finally` elimina sus contenedores, red y volúmenes temporales.

Reproducción:

```bash
uv run --locked python scripts/smoke_persistence.py
# O una variante:
uv run --locked python scripts/smoke_persistence.py --variant vector-redis
```

Los logs por variante y el resumen JSON quedan en
`output/persistence-verification/`. Los tests externos usan namespaces únicos;
no ejecutan FLUSHDB ni borran registros de otros namespaces.

## Versiones comprobadas

Plataforma: Docker Desktop 4.74.0, Engine 29.4.3, Compose 5.1.4, Linux/arm64.
API: Python 3.12.14; SQLite 3.40.1; PostgreSQL 17.11; pgvector 0.8.6;
Redis server 8.2.10; SQLAlchemy 2.0.54; Alembic 1.20.0; psycopg 3.3.6;
redis-py 8.1.0. Los digests exactos están en `scaffolding/persistence.py` y
en cada Compose generado. La matriz marca las integraciones como experimentales
con esta evidencia; no afirma soporte general en otras plataformas.

## Límites y riesgos

- El repositorio es una base reutilizable clave/valor, sin transacciones de
  múltiples operaciones ni un ORM de negocio.
- Memoria no es durable ni compartida entre procesos. Namespaces no son permisos.
- pgvector usa tres dimensiones y búsqueda exacta como ejemplo. Antes de conectar
  un modelo real hay que adaptar dimensión, migración y contratos. Float32 exige
  tolerancia al comparar distancias; no hay índice aproximado ni benchmark.
- Downgrade puede destruir datos. Solo se probó en bases aisladas; no se ofrece
  migración automática de datos de usuario ni rollback de producción.
- SQL/Redis tienen timeouts configurados; no se añaden retries de aplicación.
- TestClient mantiene el aviso de deprecación de httpx ya documentado en fase 4.
- El primer build necesita Docker Hub, PyPI y npm. No se valida producción/cloud.

## Gate 5

El mismo contrato de repositorio se ejecuta contra memoria, SQLite y PostgreSQL;
pgvector y Redis tienen contratos separados compartidos con referencias locales.
La fase 6 (proveedores AI) requiere el siguiente punto de revisión.
