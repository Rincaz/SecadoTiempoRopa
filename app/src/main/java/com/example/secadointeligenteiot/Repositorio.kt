package com.example.secadointeligenteiot

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.util.UUID

/** Resultado de intentar vaciar la cola de comandos. */
data class ResultadoCola(val enviados: Int, val descartados: Int, val pendientes: Int)

/**
 * Une API + almacenamiento local:
 *  - [actualizar]: lee el estado y lo guarda en caché; tras una caída rescata los registros perdidos.
 *  - [enviarComando]: guarda SIEMPRE primero en la cola local y luego intenta enviar (3.1.2.5 / 3.1.2.7).
 *  - [vaciarCola]: sincroniza los comandos pendientes cuando vuelve la conexión.
 */
class Repositorio(contexto: Context) {
    val store = LocalStore(contexto)
    private val candado = Mutex()          // evita vaciar la cola dos veces a la vez

    suspend fun actualizar(dispositivo: String, rescatarHistorial: Boolean): Pair<Lectura, Int> = withContext(Dispatchers.IO) {
        if (store.contarPendientes() > 0) vaciarCola()
        val lectura = ApiClient.obtenerEstado(dispositivo)
        var recuperados = 0
        if (rescatarHistorial) {
            val desde = store.ultimoTs(dispositivo).takeIf { it > 0 }
            val perdidos = ApiClient.historial(dispositivo, desde)
            perdidos.forEach { store.guardarLectura(it) }
            recuperados = perdidos.count { it.timestamp > (desde ?: Long.MAX_VALUE) }
        }
        store.guardarLectura(lectura)
        lectura to recuperados
    }

    suspend fun ultimaEnCache(dispositivo: String): Lectura? = withContext(Dispatchers.IO) { store.ultimaLectura(dispositivo) }

    suspend fun pendientes(): Int = withContext(Dispatchers.IO) { store.contarPendientes() }

    suspend fun enviarComando(dispositivo: String, actuador: String, accion: String): ResultadoCola =
        withContext(Dispatchers.IO) {
            store.encolarComando(
                ComandoPendiente(UUID.randomUUID().toString(), dispositivo, actuador, accion, System.currentTimeMillis())
            )
            vaciarCola()
        }

    suspend fun vaciarCola(): ResultadoCola = candado.withLock {
        var enviados = 0
        var descartados = 0
        for (c in store.comandosPendientes()) {
            if (!Politicas.comandoVigente(c.creadoMs, System.currentTimeMillis())) {
                store.borrarComando(c.id); descartados++; continue       // demasiado antiguo para ejecutarse sin riesgo
            }
            try {
                ApiClient.enviarComando(c)
                store.borrarComando(c.id); enviados++
            } catch (e: ErrorApi) {
                if (e.permanente) { store.borrarComando(c.id); descartados++ } else break
            } catch (e: ErrorRed) {
                break                                                     // sigue sin conexión: conservar la cola
            }
        }
        ResultadoCola(enviados, descartados, store.contarPendientes())
    }

    suspend fun cerrarSesion() = withContext(Dispatchers.IO) { store.borrarTodo() }
}
