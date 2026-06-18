# Deteccion experimental de contribucion de codigo IA

Esta carpeta contiene una PoC aislada para estimar, por escenario, commit y archivo, que rango de codigo final tiene evidencia observable de haber sido generado, sugerido, editado o influenciado por IA.

La salida es una estimacion basada en evidencia, no una prueba absoluta de autoria. El entregable consolidado principal esta en:

- [RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md](./RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md)

## Objetivo

Validar si las trazas de `session-logger` permiten correlacionar:

```text
prompt -> respuesta IA -> herramienta/editor -> archivo modificado -> diff Git -> commit final
```

El resultado esperado es un rango `AI_min` a `AI_max`, una etiqueta de confianza y una explicacion por commit y archivo.

## Alcance

Incluye:

- Analisis de los escenarios `EscenarioA/` a `EscenarioE/`.
- Carga de trazas JSON simples y OTLP.
- Extraccion de prompts, respuestas, tool calls, archivos tocados y comandos.
- Comparacion contra commits de un repositorio Git local cuando el entorno lo permite.
- Salidas JSON, CSV y Markdown por escenario.

No incluye:

- Atribucion forense absoluta.
- Cambios al backend, hooks o arquitectura principal de `session-logger`.
- Analisis de codigo que no este en trazas, diffs u outputs.

## Estructura de la carpeta

```text
propuesta-deteccion-codigo-ia/
  EscenarioA/
  EscenarioB/
  EscenarioC/
  EscenarioD/
  EscenarioE/
  config/
  outputs/
  scripts/
  tests/
  PROPUESTA_DETECCION_CODIGO_IA.md
  EXPERIMENTO_ESCENARIO_A.md
  RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md
  README.md
  requirements.txt
  Trace-2dbae2-2026-06-10 10_28_39.json
  Trace-3fff4d-2026-06-10 15_13_18.json
```

## Organizacion por escenarios

| Carpeta | Proposito | Resultado esperado | Resultado observado |
|---|---|---|---|
| `EscenarioA/` | Generacion casi completa por IA | Rango IA alto | `AI_max = 75.87%`, rango alto. |
| `EscenarioB/` | IA con edicion humana fuerte | Rango IA medio | `AI_max = 40.0%`, rango medio. |
| `EscenarioC/` | Consulta conceptual, codigo humano | Rango IA bajo | `AI_max = 0.0%`, rango muy bajo. |
| `EscenarioD/` | Notebook asistido por IA | Score sobre celdas de codigo | `AI_max = 40.46%`, requiere cautela notebook. |
| `EscenarioE/` | Dependencias/configuracion | Evidencia variable | `AI_max = 55.0%`, dominado por evidencia indirecta. |

Cada escenario tiene configuracion propia en `config/experimentX_config.json` y salidas en `outputs/EscenarioX/`.

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

## Ejecucion de pruebas

```bash
pytest tests
```

Alternativa si `pytest` no esta en PATH:

```bash
python -m pytest tests
```

Las pruebas usan fixtures locales y no requieren Git remoto ni internet.

## Ejecucion de experimentos

El runner principal es:

```bash
python scripts/run_experiment.py --config config/experimentA_config.json
```

Si Git no esta instalado o no esta en `PATH`, el experimento puede generar salidas parciales de trazas y terminar con un error claro. Para validar la orquestacion sin Git:

```bash
python scripts/run_experiment.py --config config/experimentA_config.json --dry-run
```

## Ejecucion por escenario

El script actual no expone flags `--scenario`. La ejecucion por escenario se hace con el archivo de configuracion correspondiente:

```bash
python scripts/run_experiment.py --config config/experimentA_config.json
python scripts/run_experiment.py --config config/experimentB_config.json
python scripts/run_experiment.py --config config/experimentC_config.json
python scripts/run_experiment.py --config config/experimentD_config.json
python scripts/run_experiment.py --config config/experimentE_config.json
```

## Resultados de experimentos

El consolidado tecnico-ejecutivo esta en:

```text
RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md
```

Resumen de resultados observados:

| Escenario | Commit evaluado | Archivo | AI min | AI max | Confianza |
|---|---|---|---:|---:|---|
| A | `c876d697b3e44f6b048120296a582dbb06d2b40f` | `summary_report.py` | 32.56% | 75.87% | `high_ai_evidence` |
| B | `ae852581f77044a7931b6ed5df0818bd0a70aa9b` | `scenario_b_semilla.py` | 5.0% | 40.0% | `medium_ai_evidence` |
| C | `efac6efc528b847f3efbf51157cd1b5bb612366c` | `scenario_c_manual.py` | 0.0% | 0.0% | `low_ai_evidence` |
| D | `7b8ba67e10c55218fa628eb9ec8f96e3db2a2b53` | `escenario_d_analisis_asistido_ia.ipynb` | 2.63% | 40.46% | `medium_ai_evidence` |
| E | `32ddc30ef01c98adc04d6a9a1e3d17fe09935bc4` | `requirements.txt` | 0.0% | 55.0% | `high_ai_evidence` |

## Interpretacion de resultados

- `ai_min_percent`: porcentaje minimo basado en coincidencias exactas.
- `ai_max_percent`: rango maximo ponderado con coincidencias exactas, fuzzy, estructurales e indirectas.
- `confidence_score`: confianza metodologica entre `0.0` y `1.0`.
- `confidence_label`: `no_evidence`, `low_ai_evidence`, `medium_ai_evidence`, `high_ai_evidence` o `very_high_ai_evidence`.

Rangos sugeridos:

| Rango | Lectura |
|---|---|
| 0-20% | Baja evidencia de IA |
| 20-50% | Evidencia parcial |
| 50-80% | Alta reutilizacion o influencia con posible edicion humana |
| 80-100% | Alta coincidencia con evidencia IA capturada |

Un porcentaje alto no prueba autoria absoluta. Un porcentaje bajo no prueba ausencia de IA.

## Archivos de salida

Cada escenario genera:

```text
outputs/EscenarioX/
  ai_contribution_summary.json
  ai_contribution_by_commit.csv
  ai_contribution_by_file.csv
  experiment_report.md
```

## Limitaciones

- No todas las trazas contienen codigo exacto sugerido por IA.
- Falta asociacion persistente `session_id -> commit_hash`.
- Algunas trazas incluyen ruido de archivos de la propia PoC.
- Los notebooks requieren normalizacion explicita para excluir metadata, outputs y celdas no-code.
- Cambios de dependencias pueden depender demasiado de evidencia indirecta.
- La similitud textual no prueba autoria.

## Roadmap con GitHub Copilot

1. Ejecutar escenarios controlados en ramas limpias.
2. Agregar `SCENARIO_MANIFEST.json` por escenario.
3. Capturar aceptacion/rechazo de sugerencias Copilot.
4. Guardar hashes seguros de bloques sugeridos.
5. Asociar commits con `session_id`.
6. Integrar normalizacion de notebooks en el runner.
7. Generar una vista analitica `commit_ai_contribution`.

Estructura conceptual recomendada de manifiesto:

```json
{
  "scenario": "EscenarioA",
  "hypothesis": "Generacion casi completa por Copilot",
  "target_repository": "quantum-computing-experiments",
  "branch": "experiment/copilot-a",
  "commits": ["..."],
  "trace_files": ["..."],
  "expected_ai_range": "high",
  "notes": "..."
}
```

## Preguntas frecuentes

### El score prueba que el codigo fue generado por IA?

No. El score estima contribucion o influencia con base en evidencia observable.

### Que significa `AI_min`?

Es el rango conservador basado en coincidencias exactas entre evidencia y diff.

### Que significa `AI_max`?

Es el rango ampliado que incluye evidencia fuzzy, estructural e indirecta.

### Por que Escenario C tiene interacciones IA pero score cero?

Porque la evidencia disponible no coincide de forma defendible con el codigo final. Es consistente con una consulta conceptual.

### Por que Escenario E tiene `AI_max` medio con baja similitud?

Porque su configuracion pondera mas la evidencia indirecta. Debe interpretarse con cautela.

## Proximos pasos

1. Revisar [RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md](./RESULTADOS_EXPERIMENTOS_DETECCION_CODIGO_IA.md).
2. Ejecutar `python -m pytest tests`.
3. Reejecutar cada `config/experimentX_config.json` en un entorno con Git disponible.
4. Agregar `SCENARIO_MANIFEST.json` por escenario.
5. Fortalecer captura de `session_id`, commit, diff, tool call y aceptacion Copilot.
