/*
 * Secado Inteligente IoT - Microcontrolador ESP32 (Wokwi)           Unidad 3 / TI3042
 *
 *  Sensor DHT22 --> ESP32 --(WiFi + TLS 1.2, certificado X.509)--> AWS IoT Core (MQTT, puerto 8883)
 *  Serial (monitor): el ESP32 ENVIA tramas  $DATA,<temp>,<hum>,<vent>,<calef>*HH   (3.1.3.8)
 *                    y RECIBE tramas        $CMD,<actuador>,<0|1>*HH               (3.1.3.9)
 *  Mismo protocolo que edge/protocolo.py: checksum XOR en serial, HMAC-SHA256 en MQTT.
 *
 * Pegue sus certificados en secrets.h (no comparta el enlace del proyecto con ellos dentro).
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include "mbedtls/md.h"
#include "secrets.h"

#define DISPOSITIVO "RaspberrySecadora2"   // debe coincidir con el thing y con DISPOSITIVOS de la Lambda
#define PIN_DHT 15
#define PIN_VENT 26                        // LED verde = ventilador
#define PIN_CAL 27                         // LED rojo  = calefactor

const char *TOPIC_TEL = "secadora/" DISPOSITIVO "/telemetria";
const char *TOPIC_CMD = "secadora/" DISPOSITIVO "/comando";
const char *TOPIC_ACK = "secadora/" DISPOSITIVO "/ack";

const unsigned long PERIODO_LECTURA_MS = 10000;   // el ahorro de energia viene de NO publicar si no hay cambios
const unsigned long HEARTBEAT_MS = 60000;
const int UMBRAL_TEMP = 1, UMBRAL_HUM = 2;
const long COMANDO_MAX_EDAD_S = 120;

DHT dht(PIN_DHT, DHT22);
WiFiClientSecure red;
PubSubClient mqtt(red);

bool ventilador = false, calefactor = false;
int ultTemp = -999, ultHum = -999;
bool ultV = false, ultC = false, forzarPublicar = true;
unsigned long ultLectura = 0, ultPublicacion = 0, proximoIntento = 0, esperaMs = 1000, ultWifi = 0;

// ---- almacenamiento temporal (3.1.1.4): mensajes sin enviar mientras no hay conexion
const int MAX_PEND = 20;
String pendientes[MAX_PEND];
int pendN = 0;

// ---- ids de comandos ya ejecutados (anti-repeticion)
const int MAX_IDS = 10;
String idsVistos[MAX_IDS];
int idsPos = 0;

// ============================================================ utilidades de protocolo
uint8_t xorChk(const String &s) {
  uint8_t c = 0;
  for (size_t i = 0; i < s.length(); i++) c ^= (uint8_t)s[i];
  return c;
}

void tramaSerial(const String &cuerpo) {
  char sufijo[6];
  snprintf(sufijo, sizeof sufijo, "*%02X", xorChk(cuerpo));
  Serial.println("$" + cuerpo + sufijo);
}

String hmacHex(const String &clave, const String &msg) {
  uint8_t out[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const uint8_t *)clave.c_str(), clave.length());
  mbedtls_md_hmac_update(&ctx, (const uint8_t *)msg.c_str(), msg.length());
  mbedtls_md_hmac_finish(&ctx, out);
  mbedtls_md_free(&ctx);
  String h;
  char t[3];
  for (int i = 0; i < 32; i++) { snprintf(t, sizeof t, "%02x", out[i]); h += t; }
  return h;
}

bool iguales(const String &a, const String &b) {   // comparacion en tiempo constante
  if (a.length() != b.length()) return false;
  uint8_t d = 0;
  for (size_t i = 0; i < a.length(); i++) d |= (uint8_t)(a[i] ^ b[i]);
  return d == 0;
}

bool campo(const String &js, const char *k, String &out) {   // extractor minimo de JSON plano
  String key = String("\"") + k + "\"";
  int i = js.indexOf(key);
  if (i < 0) return false;
  i = js.indexOf(':', i + key.length());
  if (i < 0) return false;
  i++;
  while (i < (int)js.length() && js[i] == ' ') i++;
  if (i >= (int)js.length()) return false;
  if (js[i] == '"') {
    int j = js.indexOf('"', i + 1);
    if (j < 0) return false;
    out = js.substring(i + 1, j);
    return true;
  }
  int j = i;
  while (j < (int)js.length() && (isdigit(js[j]) || js[j] == '-')) j++;
  out = js.substring(i, j);
  return j > i;
}

// ============================================================ actuadores
void aplicarActuador(const String &nombre, bool encender) {
  if (nombre == "ventilador") { ventilador = encender; digitalWrite(PIN_VENT, encender); }
  else if (nombre == "calefactor") { calefactor = encender; digitalWrite(PIN_CAL, encender); }
  else return;
  forzarPublicar = true;
  tramaSerial("ACK," + nombre + "," + (encender ? "1" : "0"));
}

// ============================================================ comandos por MQTT (firmados por la Lambda)
void alMensaje(char *topic, byte *payload, unsigned int len) {
  String js;
  for (unsigned int i = 0; i < len; i++) js += (char)payload[i];
  String disp, id, act, acc, ts, firma;
  if (!campo(js, "dispositivo", disp) || !campo(js, "id", id) || !campo(js, "actuador", act) ||
      !campo(js, "accion", acc) || !campo(js, "ts", ts) || !campo(js, "firma", firma)) {
    Serial.println("Comando RECHAZADO: formato");
    return;
  }
  String esperado = hmacHex(HMAC_CLAVE, disp + "|" + id + "|" + act + "|" + acc + "|" + ts);
  if (!iguales(esperado, firma)) { Serial.println("Comando RECHAZADO: firma invalida"); return; }
  if (disp != DISPOSITIVO || (act != "ventilador" && act != "calefactor") || (acc != "on" && acc != "off")) {
    Serial.println("Comando RECHAZADO: campos no permitidos");
    return;
  }
  time_t ahora = time(nullptr);
  if (ahora > 1600000000 && labs((long)ahora - ts.toInt()) > COMANDO_MAX_EDAD_S) {
    Serial.println("Comando RECHAZADO: demasiado antiguo");
    return;
  }
  for (int i = 0; i < MAX_IDS; i++) if (idsVistos[i] == id) { Serial.println("Comando duplicado ignorado"); return; }
  idsVistos[idsPos] = id;
  idsPos = (idsPos + 1) % MAX_IDS;
  aplicarActuador(act, acc == "on");
  String ack = String("{\"id\":\"") + id + "\",\"actuador\":\"" + act + "\",\"accion\":\"" + acc +
               "\",\"resultado\":\"ejecutado\"}";
  mqtt.publish(TOPIC_ACK, ack.c_str());
}

// ============================================================ telemetria
void enviarOGuardar(const String &payload) {
  if (mqtt.connected() && mqtt.publish(TOPIC_TEL, payload.c_str())) return;
  if (pendN == MAX_PEND) {                       // buffer lleno: descarta el mas antiguo
    for (int i = 1; i < MAX_PEND; i++) pendientes[i - 1] = pendientes[i];
    pendN--;
  }
  pendientes[pendN++] = payload;
  Serial.printf("Sin conexion: %d mensaje(s) guardado(s)\n", pendN);
}

void vaciarBuffer() {
  int enviados = 0;
  while (pendN > 0 && mqtt.connected() && mqtt.publish(TOPIC_TEL, pendientes[0].c_str())) {
    for (int i = 1; i < pendN; i++) pendientes[i - 1] = pendientes[i];
    pendN--;
    enviados++;
  }
  if (enviados) Serial.printf("Reconectado: %d mensaje(s) acumulado(s) enviado(s)\n", enviados);
}

void publicarTelemetria(int temp, int hum) {
  time_t ahora = time(nullptr);
  struct tm tmLocal;
  localtime_r(&ahora, &tmLocal);
  int tiempo = (int)constrain(60 + hum * 2.5 - temp * 2.0, 30.0, 480.0);
  int h = tmLocal.tm_hour < 13 ? tmLocal.tm_hour : (tmLocal.tm_hour + 1) % 24;
  uint32_t seq = (uint32_t)ahora;               // creciente (la hora viene de NTP)
  String cadena = String(DISPOSITIVO) + "|" + seq + "|" + (uint32_t)ahora + "|" + temp + "|" + hum + "|" +
                  tiempo + "|" + (ventilador ? 1 : 0) + "|" + (calefactor ? 1 : 0);
  String firma = hmacHex(HMAC_CLAVE, cadena);
  char buf[640];
  snprintf(buf, sizeof buf,
           "{\"dispositivo\":\"%s\",\"seq\":%lu,\"ts_dispositivo\":%lu,\"temperatura\":%d,\"humedad\":%d,"
           "\"tiempo_estimado_minutos\":%d,\"hora_optima\":\"%02d:00\","
           "\"actuadores\":{\"ventilador\":%s,\"calefactor\":%s},\"firma\":\"%s\"}",
           DISPOSITIVO, (unsigned long)seq, (unsigned long)ahora, temp, hum, tiempo, h,
           ventilador ? "true" : "false", calefactor ? "true" : "false", firma.c_str());
  enviarOGuardar(String(buf));
  ultPublicacion = millis();
}

// ============================================================ serial: instrucciones desde el monitor
String linea;
void procesarLinea(const String &l) {
  int fin = l.lastIndexOf('*');
  if (!l.startsWith("$") || fin < 0) { tramaSerial("ERR,FORMATO"); return; }
  String cuerpo = l.substring(1, fin), chk = l.substring(fin + 1);
  chk.trim();
  chk.toUpperCase();
  char esperado[4];
  snprintf(esperado, sizeof esperado, "%02X", xorChk(cuerpo));
  if (chk != String(esperado)) { tramaSerial("ERR,CHECKSUM"); return; }
  int a = cuerpo.indexOf(','), b = cuerpo.indexOf(',', a + 1);
  if (a < 0 || b < 0 || cuerpo.substring(0, a) != "CMD") { tramaSerial("ERR,CMD"); return; }
  String act = cuerpo.substring(a + 1, b), val = cuerpo.substring(b + 1);
  if ((act != "ventilador" && act != "calefactor") || (val != "0" && val != "1")) { tramaSerial("ERR,CMD"); return; }
  aplicarActuador(act, val == "1");
}

void leerSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (linea.length()) procesarLinea(linea);
      linea = "";
    } else if (linea.length() < 80) linea += c;
  }
}

// ============================================================ conexion con reconexion automatica (3.1.1.3)
void asegurarConexion() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - ultWifi > 5000) { ultWifi = millis(); WiFi.begin(WIFI_SSID, WIFI_PASS, 6); }
    return;
  }
  if (mqtt.connected() || millis() < proximoIntento) return;
  Serial.println("MQTT: conectando a AWS IoT...");
  if (mqtt.connect(DISPOSITIVO)) {
    Serial.println("MQTT: conectado");
    esperaMs = 1000;
    mqtt.subscribe(TOPIC_CMD, 1);
    vaciarBuffer();
  } else {
    esperaMs = min(esperaMs * 2, 60000UL);        // backoff exponencial 1 s -> 60 s
    proximoIntento = millis() + esperaMs;
    Serial.printf("MQTT: fallo (estado %d). Reintento en %lu s\n", mqtt.state(), esperaMs / 1000);
  }
}

// ============================================================ setup / loop
void setup() {
  Serial.begin(115200);
  pinMode(PIN_VENT, OUTPUT);
  pinMode(PIN_CAL, OUTPUT);
  dht.begin();
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  configTime(-3 * 3600, 0, "pool.ntp.org", "time.google.com");   // hora real: necesaria para TLS y firmas
  red.setCACert(AWS_CA);
  red.setCertificate(AWS_CERT);
  red.setPrivateKey(AWS_KEY);
  mqtt.setServer(AWS_ENDPOINT, 8883);
  mqtt.setCallback(alMensaje);
  mqtt.setBufferSize(768);
  mqtt.setKeepAlive(30);
  Serial.println("Secado Inteligente - " DISPOSITIVO " listo");
}

void loop() {
  leerSerial();
  asegurarConexion();
  mqtt.loop();

  if (millis() - ultLectura >= PERIODO_LECTURA_MS) {
    ultLectura = millis();
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (isnan(t) || isnan(h)) { tramaSerial("ERR,SENSOR"); return; }
    int temp = (int)lroundf(t), hum = (int)lroundf(h);
    tramaSerial("DATA," + String(temp) + "," + String(hum) + "," + (ventilador ? 1 : 0) + "," + (calefactor ? 1 : 0));
    bool cambio = forzarPublicar || abs(temp - ultTemp) >= UMBRAL_TEMP || abs(hum - ultHum) >= UMBRAL_HUM ||
                  ventilador != ultV || calefactor != ultC || millis() - ultPublicacion >= HEARTBEAT_MS;
    if (cambio && time(nullptr) > 1600000000) {    // sin hora NTP no se firma (evita ts invalidos)
      publicarTelemetria(temp, hum);
      ultTemp = temp; ultHum = hum; ultV = ventilador; ultC = calefactor; forzarPublicar = false;
    }
  }
}
