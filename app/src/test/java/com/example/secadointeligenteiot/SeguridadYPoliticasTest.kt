package com.example.secadointeligenteiot

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SeguridadYPoliticasTest {

    @Test
    fun sha256_vectorConocido() {
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", Hash.sha256Hex("abc"))
    }

    /** Valor calculado con Python (hashlib) -> la app y la Lambda generan la misma huella. */
    @Test
    fun huellaComando_coincideConLambda() {
        assertEquals(
            "a4d740e0a912abd74fb0e93e601a79a9579596fe321ba9363ef53343d99af490",
            Hash.huellaComando("RaspberryVirtual", "cmd-12345678", "ventilador", "on")
        )
    }

    @Test
    fun intervalo_normalAhorroYBackoff() {
        assertEquals(10_000L, Politicas.intervaloMs(0, false))
        assertEquals(60_000L, Politicas.intervaloMs(0, true))
        assertEquals(20_000L, Politicas.intervaloMs(1, false))
        assertEquals(40_000L, Politicas.intervaloMs(2, false))
        assertEquals(60_000L, Politicas.intervaloMs(10, false))   // tope
    }

    @Test
    fun ahorroEnergia_segunBateria() {
        assertTrue(Politicas.ahorroEnergia(15, cargando = false, modoAhorroSistema = false))
        assertFalse(Politicas.ahorroEnergia(15, cargando = true, modoAhorroSistema = false))
        assertTrue(Politicas.ahorroEnergia(80, cargando = false, modoAhorroSistema = true))
        assertFalse(Politicas.ahorroEnergia(80, cargando = false, modoAhorroSistema = false))
    }

    @Test
    fun comandoViejoSeDescarta() {
        val ahora = 1_000_000L
        assertTrue(Politicas.comandoVigente(ahora - 60_000, ahora))
        assertFalse(Politicas.comandoVigente(ahora - 10 * 60_000, ahora))
    }

    @Test
    fun lectura_ida_y_vuelta_json() {
        val l = Lectura("RaspberryVirtual", 24.0, 60.0, "13:00", 150, true, false, 1700000000000L, "ok", true, 4L)
        assertEquals(l, Lectura.fromJson(JSONObject(l.toJson())))
    }

    @Test
    fun comandoPendiente_ida_y_vuelta_y_cuerpoApi() {
        val c = ComandoPendiente("cmd-12345678", "RaspberryVirtual", "ventilador", "on", 5L)
        assertEquals(c, ComandoPendiente.fromJson(c.toJson()))
        assertEquals(Hash.huellaComando("RaspberryVirtual", "cmd-12345678", "ventilador", "on"),
            JSONObject(c.cuerpoApi()).getString("sha256"))
    }
}
