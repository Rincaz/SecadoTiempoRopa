package com.example.secadointeligenteiot

/** Reglas puras (sin Android) para poder probarlas con tests unitarios. */
object Politicas {

    /**
     * Intervalo entre consultas.
     *  - Con fallos consecutivos: backoff exponencial (reconexión automática, 3.1.1.3).
     *  - Con batería baja / ahorro de energía: consulta menos seguido (3.1.3.10).
     */
    fun intervaloMs(fallosConsecutivos: Int, ahorroEnergia: Boolean): Long {
        if (fallosConsecutivos > 0) {
            val factor = 1L shl minOf(fallosConsecutivos, 6)
            return minOf(ApiConfig.INTERVALO_NORMAL_MS * factor, ApiConfig.INTERVALO_MAX_MS)
        }
        return if (ahorroEnergia) ApiConfig.INTERVALO_AHORRO_MS else ApiConfig.INTERVALO_NORMAL_MS
    }

    fun ahorroEnergia(porcentajeBateria: Int, cargando: Boolean, modoAhorroSistema: Boolean): Boolean =
        modoAhorroSistema || (porcentajeBateria in 0..19 && !cargando)

    fun comandoVigente(creadoMs: Long, ahoraMs: Long): Boolean =
        ahoraMs - creadoMs <= ApiConfig.EDAD_MAX_COMANDO_MS
}
