"""Gateway de la secadora (Raspberry Pi / Raspbian) -> criterios 3.1.1.x, 3.1.3.x y 3.1.4.13.

  microcontrolador --(SERIAL, tramas $..*HH)--> gateway --(MQTT + TLS + certificados)--> AWS IoT Core
  microcontrolador <-(SERIAL, $CMD..)---------- gateway <-(MQTT, comandos firmados HMAC)- AWS IoT Core

Características:
  * TLS 1.2+ con autenticación mutua (certificado X.509 del "thing").
  * Telemetría firmada con HMAC-SHA256 + número de secuencia (integridad / anti-repetición).
  * Comandos: se verifica firma, antigüedad (<= comando_max_edad_s) e id repetido antes de actuar.
  * Reconexión automática con backoff exponencial (1 s -> 60 s) y sesión MQTT persistente.
  * Almacenamiento temporal: TODO mensaje se guarda en SQLite y se borra solo al recibir el
    PUBACK; si no hay red se acumula y se envía en orden al reconectar.
  * Ahorro de energía/ancho de banda: sólo publica si hay cambio relevante o por "heartbeat".
  * Modo seguro: si pasa mucho tiempo sin conexión, el calefactor se apaga solo.
"""
import argparse
import json
import logging
import os
import select
import sqlite3
import ssl
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
import serial

from protocolo import (ACTUADORES, armar_trama, cadena_comando, cadena_telemetria,
                       firma_valida, firmar, leer_trama)

log = logging.getLogger("gateway")


# ------------------------------------------------------------------ buffer SQLite
class BufferLocal:
    def __init__(self, ruta):
        self.db = sqlite3.connect(ruta, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS pendientes("
                            "id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, payload TEXT, creado REAL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor INTEGER)")

    def encolar(self, topic, payload) -> int:
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO pendientes(topic,payload,creado) VALUES(?,?,?)",
                                  (topic, payload, time.time()))
            return cur.lastrowid

    def pendientes(self, limite=200):
        with self.lock:
            return self.db.execute("SELECT id,topic,payload FROM pendientes ORDER BY id LIMIT ?",
                                   (limite,)).fetchall()

    def borrar(self, fila_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM pendientes WHERE id=?", (fila_id,))

    def contar(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM pendientes").fetchone()[0]

    def siguiente_seq(self) -> int:
        """Contador persistente: no se repite aunque se reinicie la Raspberry."""
        with self.lock, self.db:
            fila = self.db.execute("SELECT valor FROM meta WHERE clave='seq'").fetchone()
            n = (fila[0] if fila else 0) + 1
            self.db.execute("INSERT OR REPLACE INTO meta(clave,valor) VALUES('seq',?)", (n,))
            return n


# ------------------------------------------------------------------ gateway
class Gateway:
    def __init__(self, cfg, enlace_serial, cliente_mqtt=None):
        self.cfg = cfg
        self.disp = cfg["dispositivo"]
        self.clave = cfg["hmac_clave"]
        self.ser = enlace_serial
        self.buffer = BufferLocal(cfg.get("buffer_db", "buffer.db"))
        self.topic_tel = f"secadora/{self.disp}/telemetria"
        self.topic_cmd = f"secadora/{self.disp}/comando"
        self.topic_ack = f"secadora/{self.disp}/ack"
        self.conectado = False
        self.desconectado_desde = time.monotonic()
        self.en_vuelo = {}                      # mid -> id de fila del buffer
        self.ids_vistos = deque(maxlen=200)
        self.actuadores = {a: False for a in ACTUADORES}
        self.ultima = None                      # (temp, hum, vent, calef)
        self.ultima_pub = 0.0
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.mqtt = cliente_mqtt or self._crear_cliente_mqtt()

    # ---------------- MQTT
    def _crear_cliente_mqtt(self):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.disp,
                        clean_session=False, protocol=mqtt.MQTTv311)
        c.tls_set_context(self._contexto_tls())
        c.reconnect_delay_set(min_delay=1, max_delay=60)     # 3.1.1.3 reconexión automática
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.on_publish = self._on_publish
        return c

    def _contexto_tls(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        ctx.load_verify_locations(self.cfg["ca"])
        ctx.load_cert_chain(self.cfg["cert"], self.cfg["key"])
        return ctx

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error("Conexión rechazada: %s", reason_code)
            return
        log.info("Conectado a AWS IoT Core")
        self.conectado = True
        client.subscribe(self.topic_cmd, qos=1)
        self.vaciar_buffer()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        log.warning("Conexión perdida (%s); reintentando automáticamente", reason_code)
        self.conectado = False
        self.desconectado_desde = time.monotonic()
        self.en_vuelo.clear()

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        fila = self.en_vuelo.pop(mid, None)
        if fila is not None:
            self.buffer.borrar(fila)

    def _on_message(self, client, userdata, msg):
        self.manejar_comando(msg.payload)

    # ---------------- publicación con buffer (3.1.1.4)
    def publicar(self, topic, datos: dict):
        fila = self.buffer.encolar(topic, json.dumps(datos, separators=(",", ":")))
        if self.conectado:
            self._enviar_fila(fila, topic, json.dumps(datos, separators=(",", ":")))

    def _enviar_fila(self, fila, topic, payload):
        info = self.mqtt.publish(topic, payload, qos=1)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.en_vuelo[info.mid] = fila

    def vaciar_buffer(self):
        for fila, topic, payload in self.buffer.pendientes():
            if fila not in self.en_vuelo.values():
                self._enviar_fila(fila, topic, payload)

    # ---------------- serial -> nube
    def manejar_trama(self, campos):
        tipo = campos[0]
        if tipo == "DATA" and len(campos) == 5:
            temp, hum, vent, calef = int(campos[1]), int(campos[2]), int(campos[3]), int(campos[4])
            self.actuadores = {"ventilador": bool(vent), "calefactor": bool(calef)}
            if self._hay_cambio_relevante(temp, hum, vent, calef):
                self.publicar_telemetria(temp, hum)
        elif tipo == "ACK" and len(campos) == 3:
            log.info("ACK del microcontrolador: %s=%s", campos[1], campos[2])
            self.actuadores[campos[1]] = campos[2] == "1"
            self.ultima = None          # fuerza publicar el nuevo estado de actuadores
        elif tipo == "ERR":
            log.warning("El microcontrolador reportó error: %s", campos[1:])

    def _hay_cambio_relevante(self, temp, hum, vent, calef) -> bool:
        ahora = time.monotonic()
        previo = self.ultima
        self.ultima = (temp, hum, vent, calef)
        if previo is None or ahora - self.ultima_pub >= self.cfg.get("heartbeat_s", 60):
            return True
        return (abs(temp - previo[0]) >= self.cfg.get("umbral_temp", 1)
                or abs(hum - previo[1]) >= self.cfg.get("umbral_hum", 2)
                or (vent, calef) != (previo[2], previo[3]))

    def publicar_telemetria(self, temp, hum):
        tiempo = int(min(max(60 + hum * 2.5 - temp * 2, 30), 480))
        hora = time.localtime()
        datos = {
            "dispositivo": self.disp, "seq": self.buffer.siguiente_seq(),
            "ts_dispositivo": int(time.time()), "temperatura": temp, "humedad": hum,
            "tiempo_estimado_minutos": tiempo,
            "hora_optima": f"{(hora.tm_hour if hora.tm_hour < 13 else (hora.tm_hour + 1) % 24):02d}:00",
            "actuadores": dict(self.actuadores),
        }
        datos["firma"] = firmar(self.clave, cadena_telemetria(datos))
        self.ultima_pub = time.monotonic()
        self.publicar(self.topic_tel, datos)

    # ---------------- nube -> serial (3.1.3.9)
    def manejar_comando(self, payload) -> bool:
        try:
            d = json.loads(payload)
            if not firma_valida(self.clave, cadena_comando(d), d.get("firma")):
                log.warning("Comando RECHAZADO: firma inválida")
                return False
            if d["dispositivo"] != self.disp or d["actuador"] not in ACTUADORES or d["accion"] not in ("on", "off"):
                log.warning("Comando RECHAZADO: campos no permitidos")
                return False
            if abs(time.time() - int(d["ts"])) > self.cfg.get("comando_max_edad_s", 120):
                log.warning("Comando RECHAZADO: demasiado antiguo (posible repetición)")
                return False
            with self.lock:
                if d["id"] in self.ids_vistos:
                    log.info("Comando duplicado ignorado: %s", d["id"])
                    return False
                self.ids_vistos.append(d["id"])
        except (ValueError, KeyError, TypeError):
            log.warning("Comando RECHAZADO: JSON inválido")
            return False
        self.ser.write(armar_trama("CMD", d["actuador"], "1" if d["accion"] == "on" else "0"))
        self.publicar(self.topic_ack, {"id": d["id"], "actuador": d["actuador"], "accion": d["accion"],
                                       "ts": int(time.time()), "resultado": "enviado_al_mcu"})
        return True

    # ---------------- modo seguro (3.1.4.13)
    def revisar_modo_seguro(self):
        limite = self.cfg.get("modo_seguro_s", 300)
        if (not self.conectado and time.monotonic() - self.desconectado_desde > limite
                and self.actuadores.get("calefactor")):
            log.warning("Sin conexión > %ss: apagando calefactor por seguridad", limite)
            self.ser.write(armar_trama("CMD", "calefactor", "0"))

    # ---------------- bucles
    def bucle_serial(self):
        while not self._stop.is_set():
            linea = self.ser.readline()
            if not linea:
                continue
            campos = leer_trama(linea)
            if campos is None:
                log.warning("Trama serial corrupta descartada: %r", linea)
                continue
            try:
                self.manejar_trama(campos)
            except (ValueError, IndexError):
                log.warning("Trama serial mal formada: %r", linea)

    def correr(self):
        self.mqtt.connect_async(self.cfg["endpoint"], self.cfg.get("puerto", 8883), keepalive=30)
        self.mqtt.loop_start()
        hilo = threading.Thread(target=self.bucle_serial, daemon=True)
        hilo.start()
        try:
            while True:
                time.sleep(5)
                self.revisar_modo_seguro()
                if self.conectado and self.buffer.contar():
                    self.vaciar_buffer()
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self.mqtt.loop_stop()


class SerialPty:
    """Extremo maestro de un pseudo-terminal con la misma interfaz mínima que pyserial."""

    def __init__(self, fd, timeout=1.0):
        self.fd, self.timeout, self.buf = fd, timeout, b""

    def write(self, datos):
        os.write(self.fd, datos)

    def readline(self):
        limite = time.monotonic() + self.timeout
        while b"\n" not in self.buf:
            falta = limite - time.monotonic()
            if falta <= 0 or not select.select([self.fd], [], [], falta)[0]:
                return b""
            self.buf += os.read(self.fd, 256)
        linea, _, self.buf = self.buf.partition(b"\n")
        return linea + b"\n"


def abrir_serial(cfg):
    """Puerto real (Arduino / socat) o, si no se configura, un microcontrolador simulado interno."""
    if cfg.get("puerto_serial"):
        return serial.Serial(cfg["puerto_serial"], cfg.get("baudios", 9600), timeout=1)
    from mcu_simulador import MicrocontroladorSimulado
    maestro, esclavo = os.openpty()
    mcu = MicrocontroladorSimulado(os.ttyname(esclavo), periodo=cfg.get("periodo_mcu_s", 10))
    threading.Thread(target=mcu.correr, daemon=True).start()
    return SerialPty(maestro)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with open(args.config) as f:
        cfg = json.load(f)
    Gateway(cfg, abrir_serial(cfg)).correr()
