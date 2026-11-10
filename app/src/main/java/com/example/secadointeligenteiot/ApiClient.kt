package com.example.secadointeligenteiot

import com.google.android.gms.tasks.Task
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import javax.net.ssl.HttpsURLConnection
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Sin red / timeout / DNS: se debe reintentar más tarde (modo sin conexión). */
class ErrorRed(causa: Throwable) : Exception(causa)

/** La API respondió con error. [permanente] = reintentar no sirve (400, 403, 404). */
class ErrorApi(val codigo: Int, val permanente: Boolean) : Exception("HTTP $codigo")

private suspend fun <T> Task<T>.esperar(): T = suspendCancellableCoroutine { c ->
    addOnSuccessListener { c.resume(it) }
    addOnFailureListener { c.resumeWithException(it) }
}

/** Cliente HTTPS de la API de AWS. Todas las llamadas llevan el token de Firebase (JWT authorizer). */
object ApiClient {

    private suspend fun token(forzar: Boolean): String {
        val usuario = FirebaseAuth.getInstance().currentUser ?: throw ErrorApi(401, true)
        return try {
            usuario.getIdToken(forzar).esperar().token ?: throw ErrorApi(401, true)
        } catch (e: ErrorApi) {
            throw e
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            throw ErrorRed(e)       // sin red no se puede renovar el token
        }
    }

    private suspend fun llamar(metodo: String, ruta: String, cuerpo: String? = null): String {
        return try {
            ejecutar(metodo, ruta, cuerpo, token(false))
        } catch (e: ErrorApi) {
            if (e.codigo == 401) ejecutar(metodo, ruta, cuerpo, token(true)) else throw e   // token vencido: renovar 1 vez
        }
    }

    private suspend fun ejecutar(metodo: String, ruta: String, cuerpo: String?, token: String): String =
        withContext(Dispatchers.IO) {
            val url = URL(ApiConfig.BASE_URL + ruta)
            require(url.protocol == "https") { "Sólo se permite HTTPS" }
            var con: HttpsURLConnection? = null
            try {
                con = url.openConnection() as HttpsURLConnection
                con.requestMethod = metodo
                con.connectTimeout = ApiConfig.TIMEOUT_MS
                con.readTimeout = ApiConfig.TIMEOUT_MS
                con.setRequestProperty("Authorization", "Bearer $token")
                con.setRequestProperty("Accept", "application/json")
                if (cuerpo != null) {
                    con.doOutput = true
                    con.setRequestProperty("Content-Type", "application/json")
                    con.outputStream.use { it.write(cuerpo.toByteArray(Charsets.UTF_8)) }
                }
                val codigo = con.responseCode
                if (codigo in 200..299) {
                    con.inputStream.bufferedReader().use { it.readText() }
                } else {
                    throw ErrorApi(codigo, permanente = codigo in 400..499 && codigo != 401 && codigo != 429)
                }
            } catch (e: IOException) {
                throw ErrorRed(e)
            } finally {
                con?.disconnect()
            }
        }

    private fun q(s: String) = URLEncoder.encode(s, "UTF-8")

    suspend fun obtenerEstado(dispositivo: String): Lectura =
        Lectura.fromJson(JSONObject(llamar("GET", "/ObtenerClima?dispositivo=${q(dispositivo)}")))

    /** Registros posteriores a [desde] (o los últimos si es null). Sirve para rescatar lo ocurrido sin conexión. */
    suspend fun historial(dispositivo: String, desde: Long?): List<Lectura> {
        val extra = if (desde != null) "&desde=$desde" else ""
        val arr = JSONObject(llamar("GET", "/HistorialClima?dispositivo=${q(dispositivo)}&limite=50$extra"))
            .getJSONArray("registros")
        return (0 until arr.length()).map { Lectura.fromJson(arr.getJSONObject(it)) }
    }

    suspend fun enviarComando(c: ComandoPendiente) {
        llamar("POST", "/ComandoSecadora", c.cuerpoApi())
    }
}
