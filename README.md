# Secado Inteligente IoT (INACAP – TI3042)

App Android (Kotlin) + AWS (IoT Core, DynamoDB, Lambda, API Gateway) + gateway Raspberry (Python) + microcontrolador simulado por serial.

| Carpeta | Contenido |
|---|---|
| `app/` | App Android: monitoreo, control de actuadores, modo sin conexión, seguridad |
| `edge/` | Gateway Raspberry + microcontrolador simulado (serial, MQTT/TLS, buffer offline) |
| `backend/` | Lambda, política y regla de IoT Core, guía de despliegue en AWS Academy |
| `docs/` | Cumplimiento de la rúbrica, ISO 27001, plan de contingencia, guion del video |

Pruebas: `cd edge && python3 -m pytest -q` · `cd backend && python3 -m pytest -q` · `./gradlew test`
Empiece por `docs/CUMPLIMIENTO_RUBRICA.md`.
