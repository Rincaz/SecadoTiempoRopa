# Edge: gateway + microcontrolador (Raspberry Pi virtual)

```
MCU simulado --serial $DATA..*HH--> gateway.py --MQTT/TLS(X.509)--> AWS IoT Core
MCU simulado <-serial $CMD..*HH---- gateway.py <-MQTT comando firmado (HMAC)-- Lambda <-- App
```

## Instalar
```bash
cd edge && pip install -r requirements.txt
cp config.example.json config.json     # completar endpoint, certificados y hmac_clave
```
`hmac_clave` debe ser **idéntica** a la variable de entorno `HMAC_CLAVE` de las Lambdas.
Para otro dispositivo (p.ej. `RaspberrySecadora2`) copie `config.json`, cambie `dispositivo`,
use el certificado de ese *thing* y ejecute otra instancia.

## Ejecutar
Sin hardware (MCU simulado interno por pseudo-terminal):
```bash
python3 gateway.py --config config.json
```
Con puerto serial virtual explícito (demuestra la comunicación serial real):
```bash
socat -d -d pty,raw,echo=0,link=/tmp/ttyMCU pty,raw,echo=0,link=/tmp/ttyGW
python3 mcu_simulador.py --puerto /tmp/ttyMCU          # terminal 1
# config.json -> "puerto_serial": "/tmp/ttyGW"
python3 gateway.py --config config.json                # terminal 2
```
Con un Arduino real: `"puerto_serial": "/dev/ttyUSB0"` (mismas tramas).

## Probar
```bash
python3 -m pytest -q          # 11 pruebas: tramas, firmas, comandos, buffer offline, serial real
```
Para la demo de caída de red: `sudo ip link set eth0 down` (o apagar Wi‑Fi de la VM), esperar 1-2 min,
volver a subirla y observar en el log "Conectado..." + llegada de los datos acumulados a DynamoDB.
