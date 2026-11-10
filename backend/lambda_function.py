"""Lambda única de la API (HTTP API de API Gateway) -> criterios 3.1.1.x, 3.1.2.x, 3.1.4.x.

Rutas (todas protegidas por el JWT authorizer con tokens de Firebase Auth):
  GET  /ObtenerClima?dispositivo=X            último registro + verificación de firma HMAC
  GET  /HistorialClima?dispositivo=X&desde=T  registros posteriores a T (sincronización de la app)
  POST /ComandoSecadora                       {dispositivo,id,actuador,accion,sha256} -> MQTT firmado

Variables de entorno:
  TABLA=DatosClima  PK_NAME=dispositivo  SK_NAME=timestamp
  HMAC_CLAVE=<misma clave que edge/config.json>
  DISPOSITIVOS=RaspberryVirtual,RaspberrySecadora2
  IOT_ENDPOINT=<xxxx-ats.iot.us-east-1.amazonaws.com>   (opcional; si falta se consulta a IoT)
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ACTUADORES = ("ventilador", "calefactor")
ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")
SEGUNDOS_EN_LINEA = 180

_tabla = None
_iot = None


# ----------------------------------------------------------- firmas (iguales a edge/protocolo.py)
def _num(valor) -> str:
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


def sha256_comando(disp, cid, actuador, accion) -> str:
    """Huella que calcula la app sobre los campos del comando (integridad de extremo a extremo)."""
    return hashlib.sha256(f"{disp}|{cid}|{actuador}|{accion}".encode()).hexdigest()


# ----------------------------------------------------------- utilidades
def _json_seguro(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(type(o))


def _resp(codigo, cuerpo):
    return {"statusCode": codigo,
            "headers": {"Content-Type": "application/json", "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff"},
            "body": json.dumps(cuerpo, default=_json_seguro)}


def _dispositivos_permitidos():
    return [d.strip() for d in os.environ.get("DISPOSITIVOS", "RaspberryVirtual").split(",") if d.strip()]


def _get_tabla():
    global _tabla
    if _tabla is None:
        import boto3
        _tabla = boto3.resource("dynamodb").Table(os.environ.get("TABLA", "DatosClima"))
    return _tabla


def _get_iot():
    global _iot
    if _iot is None:
        import boto3
        endpoint = os.environ.get("IOT_ENDPOINT") or "https://" + boto3.client("iot").describe_endpoint(
            endpointType="iot:Data-ATS")["endpointAddress"]
        if not endpoint.startswith("https://"):
            endpoint = "https://" + endpoint
        _iot = boto3.client("iot-data", endpoint_url=endpoint)
    return _iot


def _usuario(event) -> str:
    claims = (event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}) or {}).get("claims", {})
    return claims.get("user_id") or claims.get("sub") or "anonimo"   # sólo el uid, nunca el correo


def _dispositivo(event):
    disp = (event.get("queryStringParameters") or {}).get("dispositivo", "RaspberryVirtual")
    return disp if disp in _dispositivos_permitidos() else None


def _consultar(disp, **extra):
    from boto3.dynamodb.conditions import Key
    pk, sk = os.environ.get("PK_NAME", "dispositivo"), os.environ.get("SK_NAME", "timestamp")
    cond = Key(pk).eq(disp)
    if "desde" in extra:
        cond = cond & Key(sk).gt(extra.pop("desde"))
    return _get_tabla().query(KeyConditionExpression=cond, **extra).get("Items", [])


def _estado_integridad(item) -> str:
    clave = os.environ.get("HMAC_CLAVE", "")
    if "firma" not in item:
        return "sin_firma"
    try:
        return "ok" if hmac.compare_digest(firmar(clave, cadena_telemetria(item)), str(item["firma"])) else "invalida"
    except (KeyError, ValueError, TypeError):
        return "invalida"


def _publico(item) -> dict:
    """Sólo los campos que la app necesita (minimización de datos)."""
    ts_dev = int(item.get("ts_dispositivo", 0))
    return {
        "dispositivo": item.get("dispositivo"),
        "temperatura": item.get("temperatura"), "humedad": item.get("humedad"),
        "hora_optima": item.get("hora_optima"),
        "tiempo_estimado_minutos": item.get("tiempo_estimado_minutos"),
        "actuadores": item.get("actuadores", {"ventilador": False, "calefactor": False}),
        "seq": item.get("seq"), "timestamp": item.get(os.environ.get("SK_NAME", "timestamp")),
        "integridad": _estado_integridad(item),
        "antiguedad_s": max(0, int(time.time()) - ts_dev) if ts_dev else None,
    }


# ----------------------------------------------------------- rutas
def obtener_clima(event):
    disp = _dispositivo(event)
    if not disp:
        return _resp(404, {"error": "dispositivo no registrado"})
    items = _consultar(disp, ScanIndexForward=False, Limit=1)
    if not items:
        return _resp(404, {"error": "sin datos"})
    r = _publico(items[0])
    r["en_linea"] = r["antiguedad_s"] is not None and r["antiguedad_s"] < SEGUNDOS_EN_LINEA
    return _resp(200, r)


def historial_clima(event):
    disp = _dispositivo(event)
    if not disp:
        return _resp(404, {"error": "dispositivo no registrado"})
    qs = event.get("queryStringParameters") or {}
    try:
        limite = min(max(int(qs.get("limite", 50)), 1), 100)
        desde = Decimal(qs["desde"]) if "desde" in qs else None
    except (ValueError, ArithmeticError):
        return _resp(400, {"error": "parámetros inválidos"})
    if desde is not None:
        items = _consultar(disp, desde=desde, ScanIndexForward=True, Limit=limite)
    else:
        items = list(reversed(_consultar(disp, ScanIndexForward=False, Limit=limite)))
    return _resp(200, {"dispositivo": disp, "registros": [_publico(i) for i in items]})


def comando_secadora(event):
    try:
        b = json.loads(event.get("body") or "{}")
        disp, cid, act, acc = b["dispositivo"], b["id"], b["actuador"], b["accion"]
    except (ValueError, KeyError, TypeError):
        return _resp(400, {"error": "cuerpo inválido"})
    if disp not in _dispositivos_permitidos():
        return _resp(404, {"error": "dispositivo no registrado"})
    if act not in ACTUADORES or acc not in ("on", "off") or not ID_VALIDO.match(str(cid)):
        return _resp(400, {"error": "comando no permitido"})
    # Integridad extremo a extremo: la huella enviada por la app debe coincidir.
    if not hmac.compare_digest(sha256_comando(disp, cid, act, acc), str(b.get("sha256", ""))):
        return _resp(400, {"error": "huella de integridad inválida"})
    msg = {"dispositivo": disp, "id": cid, "actuador": act, "accion": acc, "ts": int(time.time())}
    msg["firma"] = firmar(os.environ["HMAC_CLAVE"], cadena_comando(msg))
    _get_iot().publish(topic=f"secadora/{disp}/comando", qos=1, payload=json.dumps(msg))
    logger.info("AUDITORIA comando uid=%s disp=%s %s=%s id=%s", _usuario(event), disp, act, acc, cid)
    return _resp(202, {"id": cid, "estado": "enviado"})


RUTAS = {
    "GET /ObtenerClima": obtener_clima,
    "GET /HistorialClima": historial_clima,
    "POST /ComandoSecadora": comando_secadora,
}


def lambda_handler(event, context):
    ruta = RUTAS.get(event.get("routeKey"))
    if not ruta:
        return _resp(404, {"error": "ruta no encontrada"})
    try:
        return ruta(event)
    except Exception:                                   # no filtrar detalles internos al cliente
        logger.exception("Error interno")
        return _resp(500, {"error": "error interno"})
