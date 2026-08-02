# SMEE — Sistema de Monitoreo de Eventos Estratégicos

Prototipo determinístico en Python para transformar publicaciones de fuentes abiertas en eventos trazables. El primer conjunto de reglas se orienta a elecciones de gubernaturas de México, pero los catálogos y umbrales no están acoplados al código. Puede operar con el lote ficticio incluido o con feeds RSS públicos reales.

## Alcance de esta entrega

El flujo implementado es:

```text
JSON local o RSS → normalización → duplicados exactos → reglas → agrupación → prioridad → HTML
                                  ↓             ↓          ↓
                              SQLite        auditoría   revisión
```

El lote incluido es completamente simulado. El reporte lo indica de forma visible y no convierte sus URL ficticias en enlaces; sólo las publicaciones obtenidas por colectores reales se muestran como enlaces externos.

Incluye:

- modelos para fuentes, publicaciones, eventos, actores y coincidencias de reglas;
- creación automática del esquema SQLite y repositorios transaccionales;
- `MockCollector` para archivos JSON;
- `RSSCollector` para RSS 2.0 y Atom, sin visitar ni extraer las páginas de los artículos;
- `NewsSitemapCollector` para recuperar noticias recientes que salen rápidamente de feeds de alta frecuencia;
- normalización de texto, URL y hash SHA-256 del contenido;
- duplicidad exacta por URL normalizada o hash, conservando el duplicado, su motivo y el vínculo trazable al evento original;
- detección configurable de entidad, municipio básico, partido, actor y tipo de evento;
- reglas positivas y negativas con auditoría en `rule_matches`;
- agrupación por entidad, tipo, ventana de tres días, actores y similitud de títulos;
- puntuación explicable y niveles de importancia configurables;
- reporte HTML local con eventos, fuentes, actores, motivos de puntaje y revisión manual;
- datos demostrativos y pruebas unitarias.

## Decisiones de arquitectura

`app/pipeline.py` sólo coordina. Los colectores no conocen SQLite; el motor de reglas no genera HTML; los repositorios no contienen reglas electorales. Esto permite cambiar el origen, la persistencia o los catálogos por separado.

Se eligió YAML porque los catálogos contienen listas y estructuras jerárquicas que un analista puede revisar con mayor facilidad que JSON. Los archivos se validan al cargarse y una expresión regular inválida produce un error explícito.

El agrupamiento filtra primero por la misma entidad y tipo de evento dentro de `temporal_window_days`. Después calcula similitud de títulos con `SequenceMatcher` y agrega un bono si hay actores compartidos. Vincula al mejor candidato si supera `similarity_threshold`; candidatos casi empatados se mandan a revisión. Todos estos valores están en `config/scoring_rules.yaml`.

## Estructura

```text
smee/
├── app/
│   ├── collectors/          # contrato, MockCollector y RSSCollector
│   ├── event_detection/     # espacio para detectores especializados
│   ├── event_grouping/      # creación y vinculación de eventos
│   ├── extractors/          # reservado para extracción por fuente
│   ├── normalizers/         # texto, URL y hash
│   ├── repositories/        # SQLite y consultas
│   ├── reports/             # Jinja2 y plantilla HTML
│   ├── rules/               # clasificación determinística
│   ├── scoring/             # prioridad explicable
│   ├── utils/               # logging y similitud
│   ├── config.py
│   ├── models.py
│   └── pipeline.py
├── config/                  # catálogos y umbrales YAML
├── data/                    # entrada mock y salidas locales
├── logs/
├── tests/
├── main.py
└── requirements.txt
```

## Requisitos e instalación

- Python 3.11 o posterior.
- Windows PowerShell (comandos siguientes) o una terminal equivalente.

```powershell
cd C:\ruta\al\proyecto\smee
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux, active el entorno con `source .venv/bin/activate`.

## Ejecución

### Demostración

La ejecución predeterminada usa `data/mock_publications.json`, crea `data/smee.db` y genera `data/report.html`:

```powershell
python main.py
```

### Fuentes públicas reales

```powershell
python main.py --collector live
Start-Process .\data\rss-report.html
Start-Process .\data\reporte-electoral.xlsx
```

Este modo usa una base separada, `data/smee-rss.db`, y genera `data/rss-report.html` y `data/reporte-electoral.xlsx`. El libro incluye las hojas Eventos, Publicaciones, Actores, Revisión manual y Fuentes. Las fuentes iniciales verificadas son el feed oficial de [Central Electoral del INE](https://centralelectoral.ine.mx/feed/), el feed público de [El Financiero](https://www.elfinanciero.com.mx/arc/outboundfeeds/rss/?outputType=xml) y el [sitemap de noticias de El Congresista](https://elcongresista.mx/sitemap-news.xml). `--collector rss` sigue disponible si se desea consultar únicamente los dos feeds.

Para regenerar solamente el Excel desde la base existente, sin consultar los medios:

```powershell
python export_excel.py
```

Los colectores consultan `robots.txt`, se identifican con `User-Agent`, procesan las fuentes de forma secuencial, esperan entre solicitudes, limitan tamaño, antigüedad y cantidad de elementos, aplican timeout y sólo conservan entradas cuyo título contiene vocabulario electoral configurado. El sitemap se limita a 48 horas y a la sección política. No se descarga el contenido de los artículos.

Para usar otras rutas o una base RSS nueva:

```powershell
python main.py --collector live --database data/otra-rss.db --report data/otro-rss.html --verbose
```

Cada corrida omite una entrada que ya tenga el mismo identificador externo en la misma fuente. Un contenido repetido con identificador distinto se conserva en `publications` con estado `duplicate`, se vincula al evento original con relación `duplicate`, no cuenta como evidencia independiente y aplica el ajuste configurado de prioridad. Para repetir la demostración desde cero, use una ruta de base nueva. No borre una base con información que necesite conservar.

## Pruebas

```powershell
python -m pytest
```

Las pruebas cubren normalización, canonización de URL, hash, duplicidad exacta, reglas, ámbito nacional, ambigüedad multiestado, RSS 2.0, Atom, filtrado RSS y el flujo completo con reporte. No dependen de internet.

## Configuración

- `states.yaml`: 32 entidades, ámbito nacional, variantes y una muestra de municipios.
- `parties.yaml`: partidos y coaliciones iniciales.
- `actors.yaml`: actores demostrativos; deben sustituirse por el catálogo validado del proyecto.
- `event_types.yaml`: patrones positivos, negativos y umbrales de clasificación.
- `scoring_rules.yaml`: puntos, niveles y agrupamiento.
- `sources.yaml`: fuentes autorizadas para el lote.
- `rss_sources.yaml`: feeds reales, filtros, límites, timeout, pausa y política de robots.
- `news_sitemaps.yaml`: sitemaps públicos, ventana temporal, secciones y vocabulario electoral.
- `source_registry.yaml`: catálogo semilla nacional y estatal para descubrimiento controlado.
- `searches.yaml`: consultas reservadas para futuros colectores.

Los nombres María López, Juan Pérez y Ana Torres son datos ficticios para pruebas; no representan inferencias sobre personas reales.

## Mapa y descubrimiento de fuentes

El catálogo inicial contiene 45 semillas y al menos un medio asignado a cada entidad. Una semilla no se incorpora automáticamente al monitoreo: primero debe comprobarse que su `robots.txt` permita acceso y que publique RSS, Atom o sitemap XML válido.

Para inspeccionar Nuevo León:

```powershell
python discover_sources.py --state "Nuevo León" --limit 10 --verbose
Start-Process .\data\source-coverage.html
```

Para procesar el catálogo por lotes y evitar solicitudes excesivas:

```powershell
python discover_sources.py --offset 0 --limit 10
python discover_sources.py --offset 10 --limit 10
```

El comando genera `data/source-discovery.yaml` con endpoints y estados técnicos, y `data/source-coverage.html` con la matriz de las 32 entidades y consultas booleanas para auditoría manual. No envía esas consultas a Google ni descarga páginas de artículos.

La validación inicial de Nuevo León encontró RSS y sitemaps permitidos en El Norte. Su RSS ya fue incorporado al modo `live`. ABC Noticias permanece como fuente mapeada, pero no se activó porque no expuso XML público reconocible.

## Manejo de errores y trazabilidad

Los errores de configuración, JSON, persistencia y reglas se reportan con salida distinta de cero y se escriben en `logs/smee.log`. Cada coincidencia se conserva en `rule_matches`. Los eventos guardan `score_reasons`, mientras que publicaciones ambiguas guardan `review_reasons`.

SQLite opera con claves foráneas habilitadas y cada escritura usa transacciones con `commit` o `rollback` explícito.

## Pendiente para iteraciones posteriores

- validación periódica de disponibilidad y condiciones de uso de cada feed;
- caché HTTP condicional con `ETag` y `Last-Modified`;
- nuevos feeds estatales y extractores permitidos por cada fuente;
- duplicidad aproximada por similitud de títulos;
- municipios completos y catálogos de actores validados;
- calibración de reglas y agrupamiento con un corpus real etiquetado;
- migraciones de esquema y procesamiento incremental programado;
- cierre/descartado editorial de eventos y herramientas de revisión;
- correo, interfaz web, autenticación y otras integraciones (fuera de alcance actual).

No se incluyen IA, APIs de modelos, scraping, Selenium, Playwright, correo ni automatizaciones externas.
