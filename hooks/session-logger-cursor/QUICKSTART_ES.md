# Cursor Quick Start - Español

Guía rápida para configurar session-logger en Cursor.

## 🚀 Inicio Rápido (5 minutos)

### 1. Localiza tus hooks de Cursor

Abre un terminal y ve a tu carpeta de configuración de Cursor:

**macOS:**
```bash
cd ~/.cursor/settings/hooks
ls -la
```

**Linux:**
```bash
cd ~/.config/cursor/settings/hooks
ls -la
```

**Windows (PowerShell):**
```powershell
cd $env:APPDATA\Cursor\settings\hooks
ls
```

### 2. Copia el archivo de configuración

Desde la raíz de tu repositorio:

**macOS/Linux:**
```bash
cp hooks/session-logger-cursor/cursor-hooks.json ~/.cursor/settings/hooks/
```

**Windows:**
```powershell
copy hooks\session-logger-cursor\cursor-hooks.json $env:APPDATA\Cursor\settings\hooks\
```

### 3. Ajusta las rutas en cursor-hooks.json

Abre el archivo que acabas de copiar y busca las líneas que dicen:

```json
"bash": "... hooks/session-logger-cursor/session-logger-cursor.sh ..."
```

Reemplázalas con la ruta **absoluta** o **relativa** correcta a tu repositorio:

```json
"bash": "CURSOR_SESSION_LOGGER_LOKI_ENABLED=true CURSOR_SESSION_LOGGER_OTLP_ENABLED=true /ruta/completa/a/repo/hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted"
```

### 4. ¡Listo! 🎉

Los hooks de Cursor ahora enviarán eventos automáticamente.

---

## 📊 Verificar que funciona

### Test local sin enviar nada

```bash
cd /ruta/a/repo

# Crear un payload de prueba
cat > test_payload.json << 'EOF'
{
  "eventType": "userPromptSubmitted",
  "sessionId": "test_001",
  "cursorUser": "tu_usuario@empresa.com",
  "prompt": "Hello from Cursor!",
  "repository": "mi-repo"
}
EOF

# Ejecutar en modo simulación
CURSOR_SESSION_LOGGER_DRY_RUN=true \
bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted < test_payload.json

# Deberías ver un JSON de evento capturado
```

### Diagnóstico del sistema

```bash
bash hooks/session-logger-cursor/session-logger-cursor.sh doctor
```

Muestra:
- ✅ Rutas configuradas
- ✅ Dependencias instaladas (jq, curl)
- ✅ Endpoints de observabilidad

---

## 🔌 Conectar con Loki y OTLP (Opcional)

Si tienes la pila de observabilidad ejecutándose:

```bash
# Iniciar stack (si no está corriendo)
cd Stack-observabilidad
docker-compose -f docker-compose.observability.yml up -d
```

Luego, edita `cursor-hooks.json` y asegúrate de que:

```json
"bash": "CURSOR_SESSION_LOGGER_LOKI_ENABLED=true CURSOR_SESSION_LOGGER_LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push CURSOR_SESSION_LOGGER_OTLP_ENABLED=true CURSOR_SESSION_LOGGER_OTLP_ENDPOINT=http://localhost:4318 ..."
```

Los eventos aparecerán en:
- **Loki:** http://localhost:3100
- **Grafana:** http://localhost:3000 (admin/admin)

---

## 🐛 Si algo falla

### "Error: No se encuentra el script"

**Solución:** Verifica que la ruta en cursor-hooks.json es correcta:

```bash
# Debe retornar el contenido del script
cat /ruta/exacta/hooks/session-logger-cursor/session-logger-cursor.sh | head -5
```

### "Error: jq no encontrado"

**Solución:** Instala jq:

```bash
# macOS
brew install jq

# Linux (Debian/Ubuntu)
sudo apt-get install jq

# Linux (Fedora)
sudo dnf install jq
```

### "cursorUser no detectado"

**Solución:** Asegúrate que el payload de Cursor incluye:
```json
{
  "cursorUser": "tu_email@empresa.com"
}
```

Si no aparece, usa:
```bash
CURSOR_SESSION_LOGGER_ACTOR=mi_usuario bash hooks/session-logger-cursor/session-logger-cursor.sh --event userPromptSubmitted
```

---

## 📖 Documentación Completa

Para más detalles:
- Abre `hooks/session-logger-cursor/README.md` (documentación técnica)
- Abre `hooks/session-logger-cursor/CURSOR_INTEGRATION.md` (visión general)
- Abre `hooks/session-logger-cursor/CHANGELOG.md` (cambios implementados)

---

## ✅ Checklist de Setup

- [ ] Localicé mi carpeta de hooks de Cursor
- [ ] Copié `cursor-hooks.json`
- [ ] Ajusté las rutas en el JSON
- [ ] Testé con `CURSOR_SESSION_LOGGER_DRY_RUN=true`
- [ ] Ejecuté `doctor` para validar dependencias
- [ ] (Opcional) Configuré Loki + OTLP

---

## 🆘 Ayuda Adicional

**¿Preguntas sobre campos del payload?**
Consulta ejemplos en: `hooks/session-logger-cursor/cursor-payload-example.json`

**¿Necesitas diferentes eventos?**
Los eventos soportados son:
- `sessionStart` — Al abrir una sesión
- `userPromptSubmitted` — Cuando envías un prompt
- `preToolUse` — Antes de usar una herramienta
- `postToolUse` — Después de usar una herramienta
- `sessionEnd` — Al cerrar la sesión
- `errorOccurred` — En caso de error

---

**¿Listo para capturar eventos de Cursor?** 🚀

Ahora tus prompts en Cursor se registrarán automáticamente en el sistema de observabilidad.
