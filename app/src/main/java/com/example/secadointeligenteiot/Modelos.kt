package com.example.secadointeligenteiot

import org.json.JSONObject

data class Lectura(
    val dispositivo: String,
    val temperatura: Double,
    val humedad: Double,
    val horaOptima: String,
    val tiempoEstimadoMin: Int,
    val ventilador: Boolean,
    val calefactor: Boolean,
    val timestamp: Long,
    /** "ok" | "invalida" | "sin_firma" (verificación HMAC hecha en la nube). */
    val integridad: String,
    val enLinea: Boolean,
    val antiguedadS: Long?,
) {
    fun toJson(): String = JSONObject()
        .put("dispositivo", dispositivo).put("temperatura", temperatura).put("humedad", humedad)
        .put("hora_optima", horaOptima).put("tiempo_estimado_minutos", tiempoEstimadoMin)
        .put("actuadores", JSONObject().put("ventilador", ventilador).put("calefactor", calefactor))
        .put("timestamp", timestamp).put("integridad", integridad).put("en_linea", enLinea)
        .put("antiguedad_s", antiguedadS ?: JSONObject.NULL)
        .toString()

    companion object {
        fun fromJson(j: JSONObject): Lectura {
            val a = j.optJSONObject("actuadores")
            return Lectura(
                dispositivo = j.optString("dispositivo"),
                temperatura = j.getDouble("temperatura"),
                humedad = j.getDouble("humedad"),
                horaOptima = j.optString("hora_optima", "--:--"),
                tiempoEstimadoMin = j.optInt("tiempo_estimado_minutos", 0),
                ventilador = a?.optBoolean("ventilador", false) ?: false,
                calefactor = a?.optBoolean("calefactor", false) ?: false,
                timestamp = j.optLong("timestamp", 0L),
                integridad = j.optString("integridad", "sin_firma"),
                enLinea = j.optBoolean("en_linea", false),
                antiguedadS = if (j.isNull("antiguedad_s")) null else j.optLong("antiguedad_s"),
            )
        }
    }
}

data class ComandoPendiente(
    val id: String,
    val dispositivo: String,
    val actuador: String,   // "ventilador" | "calefactor"
    val accion: String,     // "on" | "off"
    val creadoMs: Long,
) {
    fun toJson(): String = JSONObject().put("id", id).put("dispositivo", dispositivo)
        .put("actuador", actuador).put("accion", accion).put("creado", creadoMs).toString()

    /** Cuerpo del POST: incluye la huella SHA-256 para verificar integridad en la Lambda. */
    fun cuerpoApi(): String = JSONObject().put("dispositivo", dispositivo).put("id", id)
        .put("actuador", actuador).put("accion", accion)
        .put("sha256", Hash.huellaComando(dispositivo, id, actuador, accion)).toString()

    companion object {
        fun fromJson(s: String): ComandoPendiente {
            val j = JSONObject(s)
            return ComandoPendiente(j.getString("id"), j.getString("dispositivo"), j.getString("actuador"),
                j.getString("accion"), j.getLong("creado"))
        }
    }
}
