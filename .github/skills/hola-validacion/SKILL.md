---
name: hola-validacion
description: Responde con el texto "SKILL OK: hola-validacion ejecutada" cuando el usuario quiera validar que una skill funciona en VS Code.
argument-hint: [mensaje opcional]
user-invocable: true
disable-model-invocation: false
---

# Hola validación

Usa esta skill cuando el usuario quiera probar o validar que las Agent Skills están funcionando.

## Instrucciones
1. Responde exactamente con: `SKILL OK: hola-validacion ejecutada`
2. Si el usuario proporciona texto adicional, añádelo debajo con el prefijo: `Entrada:`
3. No modifiques archivos.
4. No ejecutes scripts ni comandos de terminal.

## Ejemplos

### Ejemplo 1
Usuario: validar mi skill
Respuesta:
`SKILL OK: hola-validacion ejecutada`

### Ejemplo 2
Usuario: validar mi skill con el texto prueba 123
Respuesta:
`SKILL OK: hola-validacion ejecutada`
`Entrada: prueba 123`