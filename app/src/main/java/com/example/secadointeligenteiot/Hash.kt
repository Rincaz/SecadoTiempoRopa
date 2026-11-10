package com.example.secadointeligenteiot

import java.security.MessageDigest

/** Huellas de integridad (SHA-256). Sin dependencias de Android. */
object Hash {
    fun sha256Hex(texto: String): String =
        MessageDigest.getInstance("SHA-256").digest(texto.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    /** Debe coincidir con sha256_comando() de backend/lambda_function.py. */
    fun huellaComando(dispositivo: String, id: String, actuador: String, accion: String): String =
        sha256Hex("$dispositivo|$id|$actuador|$accion")
}
