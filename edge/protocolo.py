"""Protocolo común del dispositivo IoT (criterios 3.1.1.x, 3.1.2.x, 3.1.3.x).

Contiene:
  * Tramas seriales tipo NMEA entre el microcontrolador y el gateway:  $CUERPO*HH\\n
    (HH = checksum XOR en hexadecimal) -> detecta corrupción en el enlace serial.
  * Firma HMAC-SHA256 de los mensajes MQTT -> integridad y autenticidad extremo a extremo.
"""
import hashlib
import hmac
from functools import reduce

ACTUADORES = ("ventilador", "calefactor")


# ---------------------------------------------------------------- serial
def checksum(cuerpo: str) -> str:
    """XOR de todos los bytes del cuerpo, en 2 dígitos hexadecimales."""
    return format(reduce(lambda a, b: a ^ b, cuerpo.encode("ascii"), 0), "02X")


def armar_trama(*campos) -> bytes:
    cuerpo = ",".join(str(c) for c in campos)
    return f"${cuerpo}*{checksum(cuerpo)}\n".encode("ascii")


def leer_trama(linea) -> list[str] | None:
    """Devuelve la lista de campos o None si la trama es inválida / está corrupta."""
    if isinstance(linea, bytes):
        try:
            linea = linea.decode("ascii")
        except UnicodeDecodeError:
            return None
    linea = linea.strip()
    if not linea.startswith("$") or "*" not in linea:
        return None
    cuerpo, _, chk = linea[1:].rpartition("*")
    if checksum(cuerpo) != chk.upper():
        return None
    return cuerpo.split(",")


# ---------------------------------------------------------------- firmas
def _num(valor) -> str:
    """Formato canónico de números (acepta int, float y Decimal de DynamoDB)."""
    f = float(valor)
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def cadena_telemetria(d: dict) -> str:
    a = d.get("actuadores", {})
    return "|".join([
        str(d["dispositivo"]), str(int(d["seq"])), str(int(d["ts_dispositivo"])),
        _num(d["temperatura"]), _num(d["humedad"]), str(int(d["tiempo_estimado_minutos"])),
        "1" if a.get("ventilador") else "0", "1" if a.get("calefactor") else "0",
    ])


def cadena_comando(d: dict) -> str:
    return "|".join([str(d["dispositivo"]), str(d["id"]), str(d["actuador"]),
                     str(d["accion"]), str(int(d["ts"]))])


def firmar(clave: str, cadena: str) -> str:
    return hmac.new(clave.encode(), cadena.encode(), hashlib.sha256).hexdigest()


def firma_valida(clave: str, cadena: str, firma: str) -> bool:
    return hmac.compare_digest(firmar(clave, cadena), str(firma or ""))
