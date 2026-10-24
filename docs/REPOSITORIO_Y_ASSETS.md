# Repositorio y activos externos

## Alcance del repositorio

El repositorio `BrandonVol3/lsec-translator` contiene el código, la configuración
de ejemplo, los esquemas, los datos lingüísticos pequeños, las pruebas y los
recursos frontend necesarios para desarrollar el sistema.

El estado publicado de la rama `main` no incluye secretos ni entornos virtuales.
El archivo `.env` y `venv/` están excluidos mediante [`.gitignore`](../.gitignore).

### Contenido versionado principal

| Área | Ubicación | Propósito |
| :--- | :--- | :--- |
| Backend (API y Servicios Modulares SRP `< 800` l.) | [`app/api/`](../app/api/), [`app/services/`](../app/services/) | FastAPI, routers delgados (`animation_direct_endpoints.py`), servicios de catálogo/resolución/video (`animation_*`), motor lingüístico modular (`discourse_*`, `semantic_*`), ASR, persistencia SQLite y WebSocket |
| Frontend Modular (`< 800` l.) | [`app/static/`](../app/static/) | LSEC Studio (`index.html`), visor VRM (`viewer.html` + `js/viewer-*.js`), calibrador (`avatarconfig.html` + `js/avatarconfig-*.js`), estado (`js/state/`), motor 3D (`js/avatar/`) y sistema CSS (`css/*.css`) |
| Datos lingüísticos | [`data/`](../data/) | SQLite, lexicones, corpus piloto y guías |
| Índice VRM | [`app/data/stroke_index_v27.json`](../app/data/stroke_index_v27.json) | Índice de trazos de la versión v2.7 |
| Pruebas | [`app/tests/`](../app/tests/) | Pruebas unitarias, integración y E2E |
| Herramientas | [`tools/`](../tools/) | Utilidades de medición y validación |
| Configuración | [`.env.example`](../.env.example), [`requirements.txt`](../requirements.txt) | Preparación del entorno |

El checkout local contiene aproximadamente 64 MB de archivos versionados. La
base de código no debe confundirse con el tamaño total de la instalación local,
que incluye el entorno virtual y los activos multimedia externos.

## Activos fuera de Git

Los siguientes recursos se mantienen fuera del repositorio por su tamaño,
naturaleza binaria o ciclo de generación:

| Recurso | Ubicación esperada | Estado local verificado | Uso |
| :--- | :--- | :--- | :--- |
| Modelo VRM | `..\Avatar\LSEC-Interpreter-Female.vrm` | Disponible, 1 archivo | Avatar humanoide servido por `/avatar` |
| Animaciones v2.7 | `..\Diccionario LSEC\senas_vrm_standardized_v2.7` | Disponible, 12.429 archivos | Catálogo predeterminado estandarizado |
| Animaciones v2.6 | `..\Diccionario LSEC\senas_vrm_direct_v2.6` | Disponible, 12.434 archivos | Compatibilidad corregida |
| Videos Ultra HD | `..\Diccionario LSEC\senas_ultra_hd` | Disponible, 11.284 archivos | Referencias y exportación |
| Videos de prueba | `..\Videos de Prueba` | Disponible, 4 archivos | Pruebas manuales y modo debug |
| Pesos Whisper | `data\models\whisper` | Deben verificarse por instalación | Transcripción ASR offline |

El catálogo completo externo ocupa aproximadamente 30 GB. No se debe añadir
recursivamente `Diccionario LSEC`, `Avatar` o los modelos a un commit normal.
Para distribuirlos, se recomienda un paquete de assets versionado, Git LFS o
un almacenamiento separado con manifiestos y hashes.

## Perfiles de instalación

### Perfil mínimo: backend y traducción de texto

Requiere:

1. Python compatible.
2. Dependencias de [`requirements.txt`](../requirements.txt).
3. Modelo `es_core_news_sm` instalado.
4. [`data/`](../data/).
5. Una copia de [`.env.example`](../.env.example) como `.env`.

Permite:

- `/docs`
- `/api/info`
- `/api/v1/health`
- `/api/v1/translate`
- Persistencia SQLite
- LSEC Studio sin reproducción completa de assets externos

### Perfil ASR offline

Además del perfil mínimo, requiere los pesos locales configurados mediante
`WHISPER_MODEL_PATH`. La ruta por defecto es:

```text
data\models\whisper
```

Si los pesos no están disponibles, la traducción de texto puede seguir
funcionando, pero las rutas de transcripción y pipeline de audio no deben
considerarse operativas.

### Perfil completo audiovisual y VRM

Además del perfil ASR, requiere:

- El modelo VRM en `..\Avatar\`.
- Animaciones v2.7 en `..\Diccionario LSEC\senas_vrm_standardized_v2.7`.
- Videos Ultra HD si se necesitan referencias multimedia.
- Codecs disponibles para la finalización MP4.

Permite el flujo completo de `/studio`, `/viewer`, `/avatarconfig`,
resolución de señas y exportación audiovisual.

## Variables de rutas externas

Para una instalación distinta de la estructura recomendada, configurar:

```text
LSEC_ANIMATIONS_V27_DIR
LSEC_ANIMATIONS_V26_DIR
LSEC_ANIMATIONS_DIR
LSEC_UHD_DIR
LSEC_SENAS_DIR
```

Las rutas deben usar la ubicación real del equipo. El servidor intenta resolver
la v2.7 como versión predeterminada y conserva fallbacks explícitos para v2.6
y v2.5.

> Nota: [`run_studio.bat`](../run_studio.bat) establece explícitamente las
> rutas v2.7, v2.6 y v2.5. La v2.7 tiene prioridad para la resolución
> predeterminada.

## Comprobación de una instalación

La suite de pruebas está clasificada con marcadores pytest: `unit`,
`integration`, `assets`, `e2e` y `live_server`. Para validar una instalación
mínima se puede ejecutar `pytest -m "unit or integration"`; los perfiles
audiovisual y de navegador deben ejecutar además `pytest -m assets` y
`pytest -m e2e`, respectivamente.

Desde la raíz del proyecto:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Después comprobar:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/info
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health
Invoke-WebRequest http://127.0.0.1:8000/studio
```

Para verificar los perfiles sin escanear los catálogos multimedia:

```powershell
python tools\verify_external_assets.py
```

La utilidad solo comprueba la existencia de las rutas configuradas o
autodetectadas; no calcula hashes ni carga videos, animaciones o pesos de
modelos.

La respuesta de `/api/v1/health` debe utilizarse para distinguir una
instalación mínima de una instalación completa. La disponibilidad del backend
no implica que el catálogo VRM o los pesos ASR estén instalados.

## Política de publicación

No publicar en Git:

- `.env`, tokens, certificados o claves.
- `venv/`, cachés y resultados temporales.
- Videos originales o catálogos VRM completos.
- Pesos de modelos sin un mecanismo de distribución documentado.
- Datos de revisión que no tengan consentimiento explícito.

Sí publicar:

- Código fuente y pruebas.
- Esquemas y manifiestos pequeños.
- `.env.example` sin secretos.
- Metadatos, hashes y documentación de instalación de assets.
