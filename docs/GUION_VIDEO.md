# Guion del video demostrativo (≈ 6–7 min) – criterio 3.1.4.14

1. **Presentación (30 s):** problema (secado de ropa), arquitectura (diagrama de CUMPLIMIENTO_RUBRICA.md).
2. **Microcontrolador y serial (1 min, 3.1.3.8/9):** terminal con `socat`, `mcu_simulador.py` mostrando `$DATA…*HH`; enviar un `$CMD` y ver `$ACK`; mostrar el checksum rechazando una trama corrupta.
3. **Gateway + nube (1 min):** log del gateway publicando por MQTT/TLS; MQTT test client en AWS IoT; registro en DynamoDB con `firma`.
4. **App – monitoreo (1 min, 3.1.2.6):** login, chips de dispositivo (`RaspberryVirtual` / `RaspberrySecadora2`), temperatura, humedad, hora recomendada, sello "firma HMAC válida".
5. **App – actuadores (1 min, 3.1.2.5):** activar ventilador/calefactor y ver confirmación + `ACK` en el log del gateway.
6. **Sin conexión (1.5 min, 3.1.1.3/4, 3.1.2.7, 3.1.4.13):** modo avión → banner naranja y caché; pulsar un switch (queda "en espera"); apagar la red del gateway; restablecer → cola enviada, "N registros recuperados".
7. **Seguridad (1 min, 3.1.1.1/2, 3.1.4.11/12):** `curl` sin token → 401; alterar un registro → "firma inválida"; mostrar tabla ISO 27001; cerrar sesión y borrar datos.
8. **Energía y ajustes finales (30 s, 3.1.3.10 / 3.1.4.14):** modo ahorro (60 s), publicación por umbral; mencionar la retroalimentación recibida y los ajustes hechos.

## Checklist de entrega en el AAI
- [ ] Bloc de notas (.txt) con: link del video + link de GitHub (`https://github.com/Rincaz/SecadoTiempoRopa`).
- [ ] Repositorio sin certificados, claves ni `config.json` (revisar con `git status`).
- [ ] Subir **antes** de que termine la clase (no por correo).
