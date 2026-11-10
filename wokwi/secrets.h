// PLANTILLA: reemplace los valores. NO suba este archivo con datos reales ni comparta el proyecto con ellos.
#pragma once
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""
#define AWS_ENDPOINT "XXXXXXXXXXXXXX-ats.iot.us-east-1.amazonaws.com"   // IoT Core > Configuracion > Device data endpoint
#define HMAC_CLAVE "CAMBIAR-por-la-HMAC_CLAVE-de-la-Lambda"

static const char AWS_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
PEGUE AQUI AmazonRootCA1.pem
-----END CERTIFICATE-----
)EOF";

static const char AWS_CERT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
PEGUE AQUI EL CERTIFICADO DEL THING (xxxx-certificate.pem.crt)
-----END CERTIFICATE-----
)EOF";

static const char AWS_KEY[] PROGMEM = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
PEGUE AQUI LA CLAVE PRIVADA (xxxx-private.pem.key)
-----END RSA PRIVATE KEY-----
)EOF";
