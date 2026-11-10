"""Pruebas de la Lambda (sin AWS):  cd backend && python3 -m pytest -q"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge"))
import lambda_function as lf          # noqa: E402
import protocolo as edge              # noqa: E402

CLAVE = "clave-de-prueba"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("HMAC_CLAVE", CLAVE)
    monkeypatch.setenv("DISPOSITIVOS", "RaspberryVirtual,RaspberrySecadora2")


class IotFalso:
    def __init__(self):
        self.publicados = []

    def publish(self, **kw):
        self.publicados.append(kw)


def item(**kw):
    d = {"dispositivo": "RaspberryVirtual", "seq": 7, "ts_dispositivo": int(time.time()),
         "temperatura": 25, "humedad": 55, "tiempo_estimado_minutos": 120, "hora_optima": "13:00",
         "actuadores": {"ventilador": True, "calefactor": False}, "timestamp": 1700000000000}
    d.update(kw)
    d["firma"] = edge.firmar(CLAVE, edge.cadena_telemetria(d))
    return d


def test_firmas_identicas_a_las_del_edge():
    d = item()
    assert lf.cadena_telemetria(d) == edge.cadena_telemetria(d)
    c = {"dispositivo": "X", "id": "abc", "actuador": "ventilador", "accion": "on", "ts": 5}
    assert lf.cadena_comando(c) == edge.cadena_comando(c)


def test_estado_ok_y_manipulado(monkeypatch):
    monkeypatch.setattr(lf, "_consultar", lambda disp, **k: [item()])
    r = json.loads(lf.lambda_handler({"routeKey": "GET /ObtenerClima"}, None)["body"])
    assert r["integridad"] == "ok" and r["en_linea"] is True and r["temperatura"] == 25
    monkeypatch.setattr(lf, "_consultar", lambda disp, **k: [{**item(), "temperatura": 99}])
    r = json.loads(lf.lambda_handler({"routeKey": "GET /ObtenerClima"}, None)["body"])
    assert r["integridad"] == "invalida"


def test_dispositivo_no_registrado():
    ev = {"routeKey": "GET /ObtenerClima", "queryStringParameters": {"dispositivo": "Otro"}}
    assert lf.lambda_handler(ev, None)["statusCode"] == 404


def test_comando_publica_mensaje_firmado(monkeypatch):
    iot = IotFalso()
    monkeypatch.setattr(lf, "_get_iot", lambda: iot)
    body = {"dispositivo": "RaspberryVirtual", "id": "cmd-12345678", "actuador": "ventilador", "accion": "on"}
    body["sha256"] = lf.sha256_comando(*body.values())
    r = lf.lambda_handler({"routeKey": "POST /ComandoSecadora", "body": json.dumps(body)}, None)
    assert r["statusCode"] == 202
    pub = iot.publicados[0]
    assert pub["topic"] == "secadora/RaspberryVirtual/comando"
    msg = json.loads(pub["payload"])
    assert edge.firma_valida(CLAVE, edge.cadena_comando(msg), msg["firma"])


@pytest.mark.parametrize("cambio", [{"accion": "explotar"}, {"actuador": "horno"}, {"id": "x"},
                                    {"dispositivo": "Otro"}, {"sha256": "00"}])
def test_comando_invalido_no_publica(monkeypatch, cambio):
    iot = IotFalso()
    monkeypatch.setattr(lf, "_get_iot", lambda: iot)
    body = {"dispositivo": "RaspberryVirtual", "id": "cmd-12345678", "actuador": "ventilador", "accion": "on"}
    body["sha256"] = lf.sha256_comando(*body.values())
    body.update(cambio)
    r = lf.lambda_handler({"routeKey": "POST /ComandoSecadora", "body": json.dumps(body)}, None)
    assert r["statusCode"] in (400, 404) and iot.publicados == []


def test_historial_orden_cronologico(monkeypatch):
    monkeypatch.setattr(lf, "_consultar",
                        lambda disp, **k: [item(timestamp=3), item(timestamp=2), item(timestamp=1)])
    r = json.loads(lf.lambda_handler({"routeKey": "GET /HistorialClima"}, None)["body"])
    assert [x["timestamp"] for x in r["registros"]] == [1, 2, 3]
