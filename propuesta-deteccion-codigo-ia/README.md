# PoC de deteccion de contribucion IA

Esta carpeta contiene una propuesta tecnica y una PoC aislada para estimar, por commit y archivo, que rango de codigo final tiene evidencia observable de haber sido generado, sugerido, editado o influenciado por IA.

La PoC usa trazas de `session-logger`, evidencia de prompts y tool calls, diffs Git y similitud textual. El resultado es un rango defendible, no una verdad absoluta.

## Que hace

- Carga trazas JSON simples y trazas OTLP con `batches/instrumentationLibrarySpans/spans`.
- Extrae evidencia directa e indirecta: prompts, respuestas, tool calls, archivos tocados y comandos.
- Lee commits de un repositorio Git local.
- Compara evidencia IA contra lineas agregadas en diffs.
- Calcula `AI_min`, `AI_max`, confianza y etiqueta por commit y archivo.
- Genera salidas JSON, CSV y Markdown en `outputs/`.

## Que no hace

- No modifica el backend, hooks ni arquitectura principal de `session-logger`.
- No prueba autoria con certeza absoluta.
- No depende de internet para pruebas.
- No requiere dependencias pesadas.
- No clona repositorios durante tests.

## Instalacion

Linux/macOS:

```bash
cd propuesta-deteccion-codigo-ia
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd propuesta-deteccion-codigo-ia
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Pruebas

```bash
pytest tests
```

Alternativa si `pytest` no esta en PATH:

```bash
python -m pytest tests
```

Las pruebas usan fixtures locales y no requieren Git remoto ni internet.

## Ejecutar experimento con las trazas reales

```bash
python scripts/run_experiment.py --config config/experiment_config.example.json
```

Si Git no esta instalado o no esta en `PATH`, el experimento escribe un reporte parcial de trazas y termina con un error claro.

Para validar la orquestacion sin Git:

```bash
python scripts/run_experiment.py --config config/experiment_config.example.json --dry-run
```

## Apuntar a `quantum-computing-experiments`

La configuracion por defecto usa:

```json
"local_path": "../quantum-computing-experiments"
```

El runner intenta resolver esa ruta desde el directorio actual, desde `config/`, desde la carpeta de la PoC y desde el padre del repositorio `session-logger`. Si el repo local esta en otra ubicacion, edita `config/experiment_config.example.json` o crea una copia local de configuracion.

Para analizar un commit especifico:

```json
"commit": "HASH_DEL_COMMIT",
"commit_range": null
```

Para analizar un rango:

```json
"commit": null,
"commit_range": "BASE..HEAD"
```

## Interpretar resultados

- `ai_min_percent`: porcentaje minimo basado solo en coincidencias exactas de lineas.
- `ai_max_percent`: rango maximo ponderado con coincidencias exactas, fuzzy, estructurales e indirectas.
- `confidence_score`: confianza metodologica entre `0.0` y `1.0`.
- `confidence_label`: `no_evidence`, `low_ai_evidence`, `medium_ai_evidence`, `high_ai_evidence` o `very_high_ai_evidence`.

Rangos sugeridos:

- `0-20%`: baja evidencia de IA.
- `20-50%`: evidencia parcial.
- `50-80%`: alta reutilizacion con posible edicion humana.
- `80-100%`: alta coincidencia con evidencia IA capturada.

## Archivos de salida

```text
outputs/
├── ai_contribution_summary.json
├── ai_contribution_by_commit.csv
├── ai_contribution_by_file.csv
└── experiment_report.md
```

## Extender con nuevas trazas de GitHub Copilot

1. Copia nuevas trazas JSON dentro de esta carpeta o referencia rutas absolutas en la configuracion.
2. Agrega los archivos a `trace_files`.
3. Configura `target_repository.local_path`.
4. Define `commit` o `commit_range`.
5. Ejecuta `python scripts/run_experiment.py --config config/tu_config.json`.

## Roadmap de pruebas controladas con Copilot

Escenario A: generacion casi completa por Copilot.
1. Crear rama experimental.
2. Pedir a Copilot generar una funcion nueva.
3. Aceptar casi todo el codigo.
4. Hacer commit.
5. Ejecutar la PoC.
6. Esperar rango IA alto.

Escenario B: generacion por Copilot con edicion humana fuerte.
1. Pedir a Copilot una primera version.
2. Reescribir manualmente nombres, estructura y logica parcial.
3. Hacer commit.
4. Ejecutar la PoC.
5. Esperar rango IA medio.

Escenario C: codigo humano con consulta conceptual a Copilot.
1. Preguntar a Copilot por una explicacion.
2. Escribir manualmente el codigo.
3. Hacer commit.
4. Ejecutar la PoC.
5. Esperar rango IA bajo o indirecto.

Escenario D: notebook generado con asistencia IA.
1. Pedir a Copilot generar celdas de analisis.
2. Ejecutar notebook.
3. Guardar con outputs.
4. Hacer commit.
5. Ejecutar normalizacion de notebook.
6. Comparar solo celdas de codigo.
7. Esperar score basado en codigo, no metadata ni outputs.

Escenario E: cambios en dependencias o configuracion.
1. Pedir a Copilot sugerir dependencias.
2. Modificar `requirements.txt`.
3. Hacer commit.
4. Ejecutar la PoC.
5. Evaluar si la evidencia es directa, fuzzy o indirecta.
