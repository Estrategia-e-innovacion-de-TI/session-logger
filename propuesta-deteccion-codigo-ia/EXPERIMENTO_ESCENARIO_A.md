# Experimento Escenario A: Detección de Función Generada/Editada por IA

**Fecha:** 2026-06-18  
**Proyecto Target:** `quantum-computing-experiments`  
**Rama:** `test`  
**Commit:** `c876d69`

## Objetivo del Experimento

Validar las herramientas de detección de contribución IA usando un caso controlado donde:
1. Una función nueva es creada con características que podrían indicar generación/edición por IA
2. Se capturan trazas de sesión del cambio
3. Se ejecutan los análisis de similitud y scoring de contribución
4. Se comparan los resultados contra análisis manual Git

## Cambio Introducido

**Función:** `analizar_convergencia_cuantica()`  
**Ubicación:** `summary_report.py`  
**Tipo:** Nueva función (86 líneas agregadas)  
**Propósito:** Analizar convergencia comparativa de métodos Monte Carlo clásico vs Quantum Monte Carlo

### Características de la Función

- **Documentación completa:** Docstring extenso con Args, Returns, Raises
- **Validación robusta:** Múltiples validaciones de entrada (tipos, rangos, consistencia)
- **Lógica coherente:** Integra las funciones existentes (`calcular_estadisticas`, `rolling_average`) de forma natural
- **Ejemplos incluidos:** Se agregó caso de uso en `if __name__ == "__main__":`

### Código Agregado

```python
def analizar_convergencia_cuantica(resultados_mc, resultados_qmc, valor_referencia):
    """
    Analiza la convergencia de los métodos clásico y cuántico hacia un valor de referencia.
    
    Calcula para ambos métodos:
    - Errores acumulativos a medida que procesa más muestras.
    - Velocidad de convergencia comparativa.
    - Punto de convergencia (donde el error se estabiliza bajo un umbral).
    
    Args:
        resultados_mc: Lista de estimaciones del método clásico (float).
        resultados_qmc: Lista de estimaciones del método cuántico (float).
        valor_referencia: Valor verdadero/esperado para comparación (float).
    
    Returns:
        dict: Contiene errores acumulados, promedios finales, 
              punto de convergencia y método con mejor convergencia.
    
    Raises:
        ValueError: Si las listas tienen diferente longitud o están vacías.
    """
    # [implementación con manejo exhaustivo de casos]
```

## Indicadores Analizables para Detección

| Aspecto | Valor | Observación |
|---------|-------|-------------|
| **Similitud textual** | Media-Alta | Uso de patrones NumPy estándar, variable naming predecible |
| **Coherencia con contexto** | Alta | Se integra naturalmente con funciones existentes |
| **Documentación** | Formal | Docstring con formato estándar (Args/Returns/Raises) |
| **Manejo de errores** | Robusto | Validaciones preventivas (type casting, rangos) |
| **Complejidad ciclomática** | Moderada | Control flow directo, sin anidamientos profundos |
| **Patrones comunes** | Sí | `np.asarray()`, `np.mean()`, comprehensions, pattern matching |

## Métrica Git (Línea Base)

```bash
$ git show c876d69 --stat
 summary_report.py | 86 insertions(+)
```

**Diff Cuantitativo:**
- **Líneas agregadas:** 86
- **Funciones nuevas:** 1
- **Ejemplos agregados:** 1
- **Archivo principal modificado:** summary_report.py

## Casos de Análisis Esperados

### Caso 1: Análisis de Similitud Textual
- **Entrada:** Trazas de sesión (si las hay) vs diff Git
- **Salida esperada:** Score de similitud fuzzy ~70-85% (algunas variaciones en nombres/espacios)

### Caso 2: Análisis de Patrones IA
- **Entrada:** Docstring, validaciones, estructura
- **Indicadores:** 
  - Docstring exhaustivo ✓
  - Validaciones múltiples ✓
  - Use de comprehensions ✓
  - Pattern matching (next() con generator) ✓

### Caso 3: Integración Contextual
- **Entrada:** Funciones vecinas (`calcular_estadisticas`, `rolling_average`)
- **Resultado:** Función nueva usa patrones coherentes (NumPy, tipos float, dict returns)

## Hipótesis de Detección

**Hipótesis A (Generada por IA):**
```
P(IA) = 0.60 | evidencia: docstring exhaustivo, patrones estándar, 
              validaciones predecibles, integración automática
```

**Hipótesis B (Editada por Humano):**
```
P(Humano) = 0.40 | evidencia: sin trazas de sesión capturadas, 
                    commit message manual, integración selectiva
```

## Próximos Pasos

1. **Capturar trazas:** Ejecutar con session-logger habilitado para futuras iteraciones
2. **Ejecutar análisis:** Usar scripts de `ai_code_similarity.py` y `ai_contribution_scorer.py`
3. **Validar scoring:** Comparar rangos `AI_min-AI_max` contra hipótesis manual
4. **Documentar hallazgos:** Actualizar este reporte con resultados

## Archivos de Referencia

- [Commit en Git](file:///Users/jomaver/Desktop/Code/quantum-computing-experiments/.git)
- [Función en código](file:///Users/jomaver/Desktop/Code/quantum-computing-experiments/summary_report.py)
- [Propuesta técnica](./PROPUESTA_DETECCION_CODIGO_IA.md)

---

**Estado:** Escenario A completado ✓  
**Próxima ejecución:** Escenario B (con trazas de sesión capturadas)
