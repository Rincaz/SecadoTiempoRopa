package com.example.secadointeligenteiot

/** Configuración central. Sólo HTTPS (ver network_security_config.xml). */
object ApiConfig {
    const val BASE_URL = "https://c9mo8wujsj.execute-api.us-east-1.amazonaws.com/default"

    /** Dispositivos registrados (deben coincidir con DISPOSITIVOS de la Lambda). */
    val DISPOSITIVOS = listOf("RaspberryVirtual", "RaspberrySecadora2")

    /** Control de actuadores: se activa (true) cuando se conecten los dispositivos externos. */
    const val ACTUADORES_HABILITADOS = false

    const val TIMEOUT_MS = 8_000
    const val INTERVALO_NORMAL_MS = 10_000L
    const val INTERVALO_AHORRO_MS = 60_000L
    const val INTERVALO_MAX_MS = 60_000L

    /** Un comando guardado sin conexión se descarta si supera esta edad (seguridad: no encender un calefactor "tarde"). */
    const val EDAD_MAX_COMANDO_MS = 5 * 60_000L
    const val MAX_LECTURAS_CACHE = 200
}
