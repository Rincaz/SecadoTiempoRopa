# Microcontrolador en Wokwi (ESP32 + DHT22 + 2 LEDs)

Reemplaza a la Raspberry/VM: es el "microcontrolador" del proyecto y habla con AWS IoT Core por WiFi (MQTT + TLS).

| Pieza | Pin | Función |
|---|---|---|
| DHT22 | GPIO 15 | temperatura y humedad |
| LED verde | GPIO 26 | ventilador |
| LED rojo | GPIO 27 | calefactor |

## Usar
1. Entre a https://wokwi.com → **New Project → ESP32**. En la pestaña de archivos reemplace `sketch.ino` y
   `diagram.json`, cree `libraries.txt` y `secrets.h` con el contenido de esta carpeta.
2. En `secrets.h` pegue: endpoint de IoT Core, `HMAC_CLAVE` de la Lambda, y los 3 archivos del *thing*
   (CA, certificado, clave privada). **No comparta el enlace del proyecto con los certificados dentro.**
3. En AWS IoT Core cree un thing llamado `RaspberrySecadora2` (o cambie `DISPOSITIVO` en el sketch),
   adjunte la política `backend/iot_policy_dispositivo.json` y use la regla `backend/iot_regla.sql`.
4. ▶ Simule. El monitor serial muestra `$DATA,24,60,0,0*HH` cada 10 s.
   Para probar la **recepción serial** escriba en el monitor (con Enter) una de estas tramas listas:
   `$CMD,ventilador,1*6F` · `$CMD,ventilador,0*6E` · `$CMD,calefactor,1*7D` · `$CMD,calefactor,0*7C`
   Responde `$ACK,...` y enciende/apaga el LED. Con checksum malo (p. ej. `$CMD,ventilador,1*00`) responde `$ERR,CHECKSUM`.
5. Mueva los sliders del DHT22: al cambiar ≥1 °C o ≥2 % se publica de inmediato; si no, cada 60 s (ahorro).

Datos en la app: el dispositivo aparece como el chip `RaspberrySecadora2`.
