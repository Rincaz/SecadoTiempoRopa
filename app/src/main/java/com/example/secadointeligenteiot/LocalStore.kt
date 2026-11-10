package com.example.secadointeligenteiot

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject

/**
 * Almacenamiento temporal en el móvil (3.1.1.4 / 3.1.2.7 / 3.1.4.13):
 *  - cola de comandos creados sin conexión (se envían al reconectar),
 *  - caché de las últimas lecturas (se muestran sin conexión),
 *  - marca del último registro sincronizado por dispositivo.
 * Todo el contenido va cifrado con CajaFuerte (AES-GCM / Keystore). No se guardan correo ni contraseña.
 */
class LocalStore(contexto: Context, private val caja: CajaFuerte = CajaFuerte()) :
    SQLiteOpenHelper(contexto.applicationContext, "secado_local.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE comandos(id TEXT PRIMARY KEY, payload TEXT NOT NULL, creado INTEGER NOT NULL)")
        db.execSQL(
            "CREATE TABLE lecturas(dispositivo TEXT NOT NULL, ts INTEGER NOT NULL, payload TEXT NOT NULL, " +
                "PRIMARY KEY(dispositivo, ts))"
        )
        db.execSQL("CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
    }

    override fun onUpgrade(db: SQLiteDatabase, viejo: Int, nuevo: Int) {
        db.execSQL("DROP TABLE IF EXISTS comandos")
        db.execSQL("DROP TABLE IF EXISTS lecturas")
        db.execSQL("DROP TABLE IF EXISTS meta")
        onCreate(db)
    }

    // ---------------- cola de comandos
    fun encolarComando(c: ComandoPendiente) {
        val v = ContentValues().apply {
            put("id", c.id); put("payload", caja.cifrar(c.toJson())); put("creado", c.creadoMs)
        }
        writableDatabase.insertWithOnConflict("comandos", null, v, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun comandosPendientes(): List<ComandoPendiente> {
        val r = mutableListOf<ComandoPendiente>()
        readableDatabase.query("comandos", arrayOf("payload"), null, null, null, null, "creado ASC").use { cur ->
            while (cur.moveToNext()) {
                caja.descifrar(cur.getString(0))?.let { r += ComandoPendiente.fromJson(it) }
            }
        }
        return r
    }

    fun borrarComando(id: String) {
        writableDatabase.delete("comandos", "id = ?", arrayOf(id))
    }

    fun contarPendientes(): Int =
        readableDatabase.rawQuery("SELECT COUNT(*) FROM comandos", null).use { it.moveToFirst(); it.getInt(0) }

    // ---------------- caché de lecturas
    fun guardarLectura(l: Lectura) {
        val db = writableDatabase
        val v = ContentValues().apply {
            put("dispositivo", l.dispositivo); put("ts", l.timestamp); put("payload", caja.cifrar(l.toJson()))
        }
        db.insertWithOnConflict("lecturas", null, v, SQLiteDatabase.CONFLICT_REPLACE)
        if (l.timestamp > ultimoTs(l.dispositivo)) {
            val m = ContentValues().apply { put("clave", "ts_${l.dispositivo}"); put("valor", l.timestamp.toString()) }
            db.insertWithOnConflict("meta", null, m, SQLiteDatabase.CONFLICT_REPLACE)
        }
        // Retención limitada: sólo las últimas N lecturas por dispositivo.
        db.execSQL(
            "DELETE FROM lecturas WHERE dispositivo = ? AND ts NOT IN " +
                "(SELECT ts FROM lecturas WHERE dispositivo = ? ORDER BY ts DESC LIMIT ?)",
            arrayOf<Any>(l.dispositivo, l.dispositivo, ApiConfig.MAX_LECTURAS_CACHE)
        )
    }

    fun ultimaLectura(dispositivo: String): Lectura? =
        readableDatabase.query(
            "lecturas", arrayOf("payload"), "dispositivo = ?", arrayOf(dispositivo), null, null, "ts DESC", "1"
        ).use { cur ->
            if (cur.moveToFirst()) caja.descifrar(cur.getString(0))?.let { Lectura.fromJson(JSONObject(it)) } else null
        }

    fun ultimoTs(dispositivo: String): Long =
        readableDatabase.query("meta", arrayOf("valor"), "clave = ?", arrayOf("ts_$dispositivo"), null, null, null)
            .use { if (it.moveToFirst()) it.getString(0).toLongOrNull() ?: 0L else 0L }

    /** Cierre de sesión: no deben quedar datos del usuario en el equipo. */
    fun borrarTodo() {
        writableDatabase.apply {
            execSQL("DELETE FROM comandos"); execSQL("DELETE FROM lecturas"); execSQL("DELETE FROM meta")
        }
    }
}
