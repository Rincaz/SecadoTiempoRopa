"""Pruebas automáticas del edge:  cd edge && python3 -m pytest -q"""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from gateway import Gateway, SerialPty
from mcu_simulador import MicrocontroladorSimulado
from protocolo import armar_trama, cadena_comando, cadena_telemetria, firmar, leer_trama

CLAVE = "clave-de-prueba"


class MqttFalso:
    def __init__(self):
        self.enviados, self._mid = [], 0

    def publish(self, topic, payload, qos=0):
        self._mid += 1
        self.enviados.append((topic, json.loads(payload), self._mid))
        return type("Info", (), {"rc": mqtt.MQTT_ERR_SUCCESS, "mid": self._mid})()

    def subscribe(self, *a, **k):
        pass


class SerialFalso:
    def __init__(self):
        self.escrito = []

    def write(self, b):
        self.escrito.append(b)

    def readline(self):
        return b""


@pytest.fixture
def gw(tmp_path):
    cfg = {"dispositivo": "RaspberryVirtual", "hmac_clave": CLAVE, "buffer_db": str(tmp_path / "b.db"),
           "heartbeat_s": 60, "modo_seguro_s": 0}
    return Gateway(cfg, SerialFalso(), MqttFalso())


def comando(gw, **kw):
    d = {"dispositivo": "RaspberryVirtual", "id": "c1", "actuador": "ventilador", "accion": "on",
         "ts": int(time.time())}
    d.update(kw)
    d["firma"] = firmar(CLAVE, cadena_comando(d))
    return json.dumps(d)


# ---------------- protocolo serial
def test_trama_ida_y_vuelta():
    assert leer_trama(armar_trama("DATA", 24, 60, 0, 1)) == ["DATA", "24", "60", "0", "1"]


def test_trama_corrupta_se_descarta():
    t = bytearray(armar_trama("DATA", 24, 60, 0, 1))
    t[6] ^= 0x01
    assert leer_trama(bytes(t)) is None
    assert leer_trama(b"basura\n") is None


# ---------------- comandos (3.1.3.9)
def test_comando_valido_llega_al_mcu(gw):
    assert gw.manejar_comando(comando(gw))
    assert leer_trama(gw.ser.escrito[-1]) == ["CMD", "ventilador", "1"]


def test_comando_firma_invalida(gw):
    d = json.loads(comando(gw))
    d["accion"] = "off"          # alterado después de firmar
    assert not gw.manejar_comando(json.dumps(d))
    assert gw.ser.escrito == []


def test_comando_antiguo_y_duplicado(gw):
    assert not gw.manejar_comando(comando(gw, ts=int(time.time()) - 3600))
    assert gw.manejar_comando(comando(gw, id="x"))
    assert not gw.manejar_comando(comando(gw, id="x"))


def test_comando_actuador_no_permitido(gw):
    assert not gw.manejar_comando(comando(gw, actuador="horno"))


# ---------------- telemetría y buffer (3.1.3.8 / 3.1.1.4)
def test_telemetria_firmada_y_con_secuencia(gw):
    gw.conectado = True
    gw.manejar_trama(["DATA", "24", "60", "0", "0"])
    topic, d, _ = gw.mqtt.enviados[-1]
    assert topic == "secadora/RaspberryVirtual/telemetria"
    assert d["firma"] == firmar(CLAVE, cadena_telemetria(d))
    assert d["seq"] == 1


def test_sin_conexion_se_acumula_y_se_envia_al_reconectar(gw):
    for t in (24, 30, 36):                          # cambios grandes -> 3 publicaciones
        gw.ultima_pub = 0
        gw.manejar_trama(["DATA", str(t), "60", "0", "0"])
    assert gw.buffer.contar() == 3 and gw.mqtt.enviados == []
    gw.conectado = True
    gw.vaciar_buffer()
    assert [e[1]["temperatura"] for e in gw.mqtt.enviados] == [24, 30, 36]   # en orden
    for _, _, mid in gw.mqtt.enviados:
        gw._on_publish(None, None, mid)                                       # PUBACK
    assert gw.buffer.contar() == 0


def test_umbral_evita_publicar_sin_cambios(gw):
    gw.conectado = True
    gw.manejar_trama(["DATA", "24", "60", "0", "0"])
    gw.manejar_trama(["DATA", "24", "61", "0", "0"])      # cambio < umbral
    assert len(gw.mqtt.enviados) == 1


def test_modo_seguro_apaga_calefactor(gw):
    gw.actuadores["calefactor"] = True
    gw.desconectado_desde = time.monotonic() - 10
    gw.revisar_modo_seguro()
    assert leer_trama(gw.ser.escrito[-1]) == ["CMD", "calefactor", "0"]


# ---------------- integración serial real (pty) con el microcontrolador simulado
def test_mcu_por_serial_recibe_comando_y_responde_ack():
    maestro, esclavo = os.openpty()
    mcu = MicrocontroladorSimulado(os.ttyname(esclavo), periodo=0.2)
    threading.Thread(target=mcu.correr, daemon=True).start()
    ser = SerialPty(maestro, timeout=2)
    assert leer_trama(ser.readline())[0] == "DATA"
    ser.write(armar_trama("CMD", "calefactor", "1"))
    vistos = [leer_trama(ser.readline()) for _ in range(4)]
    assert ["ACK", "calefactor", "1"] in vistos
    ser.write(b"$CMD,calefactor,0*00\n")                  # checksum incorrecto
    vistos = [leer_trama(ser.readline()) for _ in range(4)]
    assert ["ERR", "CHECKSUM"] in vistos
    mcu.detener()
