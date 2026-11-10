"""Microcontrolador simulado (hace el papel del Arduino) -> criterios 3.1.3.8 y 3.1.3.9.

Habla por puerto SERIAL con el gateway:
  * ENVÍA  $DATA,<temp>,<hum>,<ventilador>,<calefactor>*HH     cada N segundos
  * RECIBE $CMD,<actuador>,<0|1>*HH   y responde  $ACK,<actuador>,<0|1>*HH
  * Ignora (y reporta con $ERR) cualquier trama con checksum inválido.

Puerto virtual (sin hardware):
    socat -d -d pty,raw,echo=0,link=/tmp/ttyMCU pty,raw,echo=0,link=/tmp/ttyGW
    python3 mcu_simulador.py --puerto /tmp/ttyMCU
    python3 gateway.py        # con "puerto_serial": "/tmp/ttyGW" en config.json
"""
import argparse
import random
import threading
import time

import serial

from protocolo import ACTUADORES, armar_trama, leer_trama


class MicrocontroladorSimulado:
    def __init__(self, puerto, baudios=9600, periodo=10.0):
        self.ser = serial.Serial(puerto, baudios, timeout=0.5)
        self.periodo = periodo
        self.estado = {a: 0 for a in ACTUADORES}
        self.temp = 24.0
        self.hum = 60.0
        self._stop = threading.Event()

    def _sensores(self):
        # Deriva suave: el calefactor sube temperatura / baja humedad, el ventilador baja humedad.
        self.temp += random.uniform(-0.4, 0.4) + 0.6 * self.estado["calefactor"]
        self.hum += random.uniform(-1.0, 1.0) - 1.5 * self.estado["ventilador"] - 1.0 * self.estado["calefactor"]
        self.temp = min(max(self.temp, 10.0), 45.0)
        self.hum = min(max(self.hum, 20.0), 95.0)

    def enviar_datos(self):
        self._sensores()
        self.ser.write(armar_trama("DATA", round(self.temp), round(self.hum),
                                   self.estado["ventilador"], self.estado["calefactor"]))

    def procesar_entrada(self):
        linea = self.ser.readline()
        if not linea:
            return
        campos = leer_trama(linea)
        if campos is None:
            self.ser.write(armar_trama("ERR", "CHECKSUM"))
            return
        if campos[0] == "CMD" and len(campos) == 3 and campos[1] in ACTUADORES and campos[2] in ("0", "1"):
            self.estado[campos[1]] = int(campos[2])
            self.ser.write(armar_trama("ACK", campos[1], campos[2]))
        else:
            self.ser.write(armar_trama("ERR", "CMD"))

    def correr(self):
        proximo = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= proximo:
                self.enviar_datos()
                proximo = time.monotonic() + self.periodo
            self.procesar_entrada()

    def detener(self):
        self._stop.set()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", required=True)
    ap.add_argument("--baudios", type=int, default=9600)
    ap.add_argument("--periodo", type=float, default=10.0)
    a = ap.parse_args()
    MicrocontroladorSimulado(a.puerto, a.baudios, a.periodo).correr()
