# Cumplimiento de la escala de apreciación – Unidad 3 (TI3042)

Arquitectura: `App Android → HTTPS + JWT Firebase → API Gateway → Lambda → IoT Core (MQTT/TLS, HMAC) → Raspberry (gateway Python) → serial → microcontrolador (simulado)`.
Los datos de vuelta: `MCU → serial → gateway → MQTT → regla IoT → DynamoDB → Lambda → App`.

> **Sobre "comunicación serial":** el enlace *serial* real está entre el microcontrolador y el gateway
> (`edge/mcu_simulador.py` ↔ `edge/gateway.py`, tramas `$..*HH` con checksum, 9600 baudios, puerto virtual `socat`
> o `/dev/ttyUSB0` con un Arduino). La app llega a ese enlace de forma remota (HTTPS → AWS → MQTT), tal como
> indica la guía ("sensor envía por MQTT → broker → DB no estructurada → la app rescata los mensajes").
> Explíquelo así en el video.

| # | Criterio | Dónde está implementado | Cómo demostrarlo |
|---|---|---|---|
| 3.1.1.1 | Instrucciones cumplen estándares de envío seguro | `network_security_config.xml` (sin tráfico en claro), `ApiClient.kt` (sólo HTTPS + token Firebase), `gateway.py` (TLS ≥1.2 con certificado X.509), `iot_policy_dispositivo.json` (mínimo privilegio), JWT authorizer en API Gateway | `curl` sin token → 401; MQTT test client muestra conexión sólo con certificado |
| 3.1.1.2 | Integridad de datos enviados/recibidos | Telemetría firmada HMAC‑SHA256 + `seq` (`protocolo.py`, verificada en Lambda → campo `integridad`); comandos con huella SHA‑256 de la app (`Hash.kt`) y firma HMAC de la Lambda verificada por el gateway; checksum XOR en serial | Alterar un registro en DynamoDB → la app muestra "firma inválida"; test `test_comando_firma_invalida` |
| 3.1.1.3 | Reconexión automática | App: `MonitorRed.kt` + backoff exponencial (`Politicas.intervaloMs`). Gateway: `reconnect_delay_set(1,60)` + sesión MQTT persistente | Apagar Wi‑Fi del teléfono / `ip link set eth0 down` en la VM y volver a encender |
| 3.1.1.4 | Almacenamiento temporal en móvil y microcontrolador sin conexión | Móvil: `LocalStore.kt` (SQLite cifrado: cola de comandos + caché de lecturas). Gateway: `BufferLocal` (SQLite; borra sólo tras PUBACK) | Modo avión → la app muestra último dato y encola comandos; en la VM revisar `buffer.db` |
| 3.1.2.5 | App envía instrucciones | `MainActivity.kt` (switches) → `Repositorio.enviarComando` → `POST /ComandoSecadora` → MQTT → gateway → trama `$CMD` por serial | Activar ventilador y ver `ACK` en el log del gateway |
| 3.1.2.6 | App recibe instrucciones/datos | `ApiClient.obtenerEstado/historial`; la app muestra temperatura, humedad, estado real de actuadores y confirmación | Cambiar estado y ver el switch confirmarse |
| 3.1.2.7 | Almacenamiento temporal en app + sincronización | `Repositorio.vaciarCola()` (envía comandos pendientes al volver la red) y `actualizar(rescatarHistorial=true)` (rescata registros perdidos vía `/HistorialClima`) | Modo avión → pulsar switches → desactivar modo avión → banner "N registros recuperados" |
| 3.1.3.8 | Microcontrolador envía instrucciones por serial | `mcu_simulador.py` (`$DATA`, `$ACK`, `$ERR`) | Mostrar terminal del MCU/`socat -d -d` |
| 3.1.3.9 | Microcontrolador recibe instrucciones por serial | `mcu_simulador.py` procesa `$CMD`; `gateway.py` valida firma/edad/id antes de reenviar | Test `test_mcu_por_serial_recibe_comando_y_responde_ack` |
| 3.1.3.10 | Consumo de energía | App: sólo consulta en pantalla visible (`repeatOnLifecycle`), no consulta sin red, intervalo 60 s con batería <20 % o ahorro del sistema. Edge: publica sólo con cambios o heartbeat (`umbral_*`, `heartbeat_s`) | Mostrar banner "modo ahorro"; log del gateway publica menos |
| 3.1.4.11 | Conexión Android–IoT según ISO | `docs/SEGURIDAD_ISO27001.md` (mapa de controles Anexo A) | Presentar tabla + evidencias |
| 3.1.4.12 | Protección de datos personales | Sólo se usa el `uid` en logs (no correo); caché cifrada AES‑256‑GCM en Keystore; `allowBackup=false` + reglas de extracción; "Cerrar sesión y borrar datos"; TTL 30 días en DynamoDB; API devuelve sólo campos necesarios | Cerrar sesión y verificar que no quedan datos |
| 3.1.4.13 | Plan de contingencia | `docs/PLAN_CONTINGENCIA.md`; implementado: caché, cola, descarte de comandos viejos, modo seguro del gateway | Demo: cortar red, mostrar banner y recuperación |
| 3.1.4.14 | Video explicativo y ajustes finales | `docs/GUION_VIDEO.md` + checklist de entrega | Grabar y subir al AAI |

> **Nota sobre la escala:** en la imagen, el criterio **3.1.3.8** aparece con "Bueno 12.8 pts / Excelente 4.2 pts"
> (etiquetas probablemente invertidas) y es el de mayor puntaje de toda la rúbrica: priorice mostrar el
> enlace serial del microcontrolador (envío de `$DATA`) con claridad en el video.

## Lo que debe hacer usted (no se puede automatizar desde aquí)
1. Seguir `backend/DESPLIEGUE_AWS_ACADEMY.md` (Lambda nueva, rutas, JWT authorizer, política y regla IoT).
2. Copiar `edge/config.example.json` → `config.json`, certificados y `hmac_clave` (igual a `HMAC_CLAVE` de la Lambda).
3. Abrir el proyecto en Android Studio, sincronizar Gradle y ejecutar los tests (`./gradlew test`).
4. Probar en al menos 2 versiones de Android (p. ej. API 24 y API 34+) y en emulador x86_64 + equipo ARM (criterio de compatibilidad).
5. Grabar el video y entregar el bloc de notas con los links (video + GitHub) en el AAI. **No se aceptan entregas por correo.**
