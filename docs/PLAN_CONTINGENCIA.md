# Plan de contingencia y continuidad operativa (3.1.4.13)

| Falla | Detección | Respuesta automática | Recuperación |
|---|---|---|---|
| Teléfono sin Internet | `MonitorRed.onLost` / `ErrorRed` | Banner naranja, muestra último dato de la caché cifrada; los comandos se guardan en cola | Al volver la red: envío de la cola + rescate del historial perdido |
| Comando pendiente demasiado tiempo | edad > 5 min (`EDAD_MAX_COMANDO_MS`) | Se descarta (no se enciende un calefactor "tarde") | El usuario lo repite |
| Gateway/Raspberry sin Internet | `on_disconnect` | Reintentos con backoff 1→60 s; los mensajes se acumulan en `buffer.db` y se publican en orden al reconectar | Datos históricos llegan a DynamoDB |
| Caída prolongada del gateway (> `modo_seguro_s`) | `revisar_modo_seguro()` | Apaga el **calefactor** (estado seguro) | Operador reactiva desde la app |
| Comando alterado / repetido / antiguo | HMAC, `ts` ±120 s, `id` duplicado | Se rechaza y se registra | — |
| Datos alterados en la nube | HMAC de telemetría | La app muestra "firma inválida" | Revisar DynamoDB / rotar `HMAC_CLAVE` |
| Dispositivo apagado | `en_linea=false` (> 180 s sin datos) | Banner "dispositivo no reporta" | Revisar energía/red del dispositivo |
| API / Lambda caída (5xx) | `ErrorApi` | Banner rojo, reintentos con backoff | Revisar CloudWatch |
| Sesión AWS Academy expirada | Errores 5xx/timeouts | Mismo manejo que API caída | Reiniciar laboratorio y verificar recursos |
