package com.example.secadointeligenteiot

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Bundle
import android.os.PowerManager
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.button.MaterialButton
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Pantalla principal: monitoreo (sensores) + control (actuadores) de varios dispositivos IoT.
 *  - Reconexión automática: backoff exponencial + reacción inmediata al volver la red (MonitorRed).
 *  - Sin conexión: muestra el último dato guardado y encola los comandos (se envían solos al reconectar).
 *  - Ahorro de energía: no consulta sin red, ni en segundo plano; intervalo mayor con batería baja.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var repo: Repositorio
    private lateinit var monitor: MonitorRed

    private lateinit var tvEstado: TextView
    private lateinit var tvPendientes: TextView
    private lateinit var tvClima: TextView
    private lateinit var tvRecomendacion: TextView
    private lateinit var tvTiempoSecado: TextView
    private lateinit var tvIntegridad: TextView
    private lateinit var tvActualizado: TextView
    private lateinit var tvAccion: TextView
    private lateinit var swVentilador: MaterialSwitch
    private lateinit var swCalefactor: MaterialSwitch

    private val senalRed = Channel<Unit>(Channel.CONFLATED)
    private var dispositivo = ApiConfig.DISPOSITIVOS.first()
    private var hayRed = true
    private var necesitaRescate = false

    /** actuador -> (estado pedido, hasta cuándo ignorar lo que reporte el dispositivo). */
    private val esperando = mutableMapOf<String, Pair<Boolean, Long>>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        repo = Repositorio(this)
        tvEstado = findViewById(R.id.tvEstadoConexion)
        tvPendientes = findViewById(R.id.tvPendientes)
        tvClima = findViewById(R.id.tvClima)
        tvRecomendacion = findViewById(R.id.tvRecomendacion)
        tvTiempoSecado = findViewById(R.id.tvTiempoSecado)
        tvIntegridad = findViewById(R.id.tvIntegridad)
        tvActualizado = findViewById(R.id.tvActualizado)
        tvAccion = findViewById(R.id.tvAccion)
        swVentilador = findViewById(R.id.swVentilador)
        swCalefactor = findViewById(R.id.swCalefactor)

        monitor = MonitorRed(this) { conectado ->
            lifecycleScope.launch {
                hayRed = conectado
                if (conectado) senalRed.trySend(Unit) else mostrarBanner("Sin conexión · se muestran datos guardados", R.color.estado_aviso)
            }
        }

        configurarDispositivos()
        if (ApiConfig.ACTUADORES_HABILITADOS) {
            // setOnClickListener sólo se dispara por toques del usuario (no al actualizar el switch por código).
            swVentilador.setOnClickListener { enviarComando("ventilador", swVentilador.isChecked) }
            swCalefactor.setOnClickListener { enviarComando("calefactor", swCalefactor.isChecked) }
        } else {
            // Función futura: requiere dispositivos externos (ventilador / calefactor reales).
            swVentilador.isEnabled = false
            swCalefactor.isEnabled = false
            tvAccion.text = "Próximamente: se activará al conectar los dispositivos externos."
        }
        findViewById<MaterialButton>(R.id.btnSalir).setOnClickListener { cerrarSesion() }

        // Sólo consulta mientras la pantalla está visible (STARTED): en segundo plano no gasta batería ni datos.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) { bucleDeActualizacion() }
        }
    }

    override fun onStart() {
        super.onStart()
        hayRed = monitor.hayRed()
        monitor.iniciar()
    }

    override fun onStop() {
        monitor.detener()
        super.onStop()
    }

    // ------------------------------------------------------------------ dispositivos
    private fun configurarDispositivos() {
        val grupo = findViewById<ChipGroup>(R.id.chipsDispositivos)
        ApiConfig.DISPOSITIVOS.forEachIndexed { i, nombre ->
            val chip = Chip(this).apply {
                id = View.generateViewId()
                text = nombre
                isCheckable = true
                isChecked = i == 0
            }
            chip.setOnClickListener {
                if (dispositivo != nombre) {
                    dispositivo = nombre
                    esperando.clear()
                    necesitaRescate = false
                    lifecycleScope.launch {
                        repo.ultimaEnCache(nombre)?.let { mostrarLectura(it, deCache = true) }
                        senalRed.trySend(Unit)
                    }
                }
            }
            grupo.addView(chip)
        }
    }

    // ------------------------------------------------------------------ bucle de actualización
    private suspend fun bucleDeActualizacion() {
        repo.ultimaEnCache(dispositivo)?.let { mostrarLectura(it, deCache = true) }
        actualizarPendientes()
        var fallos = 0
        while (true) {
            val ok = if (hayRed) refrescar() else {
                // Sin red no se gasta energía intentando: se espera el aviso de MonitorRed.
                repo.ultimaEnCache(dispositivo)?.let { mostrarLectura(it, deCache = true) }
                mostrarBanner("Sin conexión · se muestran datos guardados", R.color.estado_aviso)
                necesitaRescate = true
                false
            }
            actualizarPendientes()
            fallos = if (ok) 0 else fallos + 1
            withTimeoutOrNull(Politicas.intervaloMs(fallos, ahorroEnergia())) { senalRed.receive() }
        }
    }

    private suspend fun refrescar(): Boolean {
        val disp = dispositivo
        return try {
            val (lectura, recuperados) = repo.actualizar(disp, necesitaRescate)
            if (disp != dispositivo) return true
            necesitaRescate = false
            mostrarLectura(lectura, deCache = false)
            val extra = if (recuperados > 0) " · $recuperados registros recuperados" else ""
            val ahorro = if (ahorroEnergia()) " · modo ahorro" else ""
            if (lectura.enLinea) mostrarBanner("En línea$extra$ahorro", R.color.estado_ok)
            else mostrarBanner("Servidor OK, pero el dispositivo no reporta hace un rato$extra", R.color.estado_aviso)
            true
        } catch (e: CancellationException) {
            throw e
        } catch (e: ErrorRed) {
            necesitaRescate = true
            repo.ultimaEnCache(disp)?.let { if (disp == dispositivo) mostrarLectura(it, deCache = true) }
            mostrarBanner("Sin conexión con AWS · reintentando automáticamente", R.color.estado_aviso)
            false
        } catch (e: ErrorApi) {
            necesitaRescate = true
            val msg = when (e.codigo) {
                401, 403 -> "Sesión no autorizada (HTTP ${e.codigo}). Cierra sesión y vuelve a entrar"
                404 -> "Aún no hay datos de $disp"
                else -> "Servidor no disponible (HTTP ${e.codigo}) · reintentando"
            }
            mostrarBanner(msg, R.color.estado_error)
            false
        } catch (e: Exception) {
            mostrarBanner("Respuesta inesperada del servidor", R.color.estado_error)
            false
        }
    }

    // ------------------------------------------------------------------ comandos
    private fun enviarComando(actuador: String, encender: Boolean) {
        val disp = dispositivo
        esperando[actuador] = encender to (System.currentTimeMillis() + 30_000L)
        tvAccion.text = "Enviando: $actuador ${if (encender) "ON" else "OFF"}…"
        lifecycleScope.launch {
            val res = try {
                repo.enviarComando(disp, actuador, if (encender) "on" else "off")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                null
            }
            tvAccion.text = when {
                res == null -> "No se pudo procesar el comando"
                res.descartados > 0 && res.pendientes == 0 && res.enviados == 0 -> "Comando rechazado por el servidor"
                res.pendientes > 0 -> "Sin conexión: el comando quedó en espera y se enviará solo"
                else -> "Comando enviado · esperando confirmación del dispositivo"
            }
            actualizarPendientes()
            delay(3_000)                  // da tiempo al dispositivo para actuar y reportar su nuevo estado
            senalRed.trySend(Unit)
        }
    }

    private suspend fun actualizarPendientes() {
        val n = repo.pendientes()
        tvPendientes.visibility = if (n > 0) View.VISIBLE else View.GONE
        tvPendientes.text = "$n comando(s) en espera de conexión"
    }

    // ------------------------------------------------------------------ UI
    private fun mostrarBanner(texto: String, colorRes: Int) {
        tvEstado.text = texto
        tvEstado.setBackgroundColor(ContextCompat.getColor(this, colorRes))
    }

    private fun mostrarLectura(l: Lectura, deCache: Boolean) {
        tvClima.text = "Temperatura: ${l.temperatura.toInt()}°C | Humedad: ${l.humedad.toInt()}%"
        tvRecomendacion.text = "Hora recomendada para tender: ${l.horaOptima} hrs"
        tvTiempoSecado.text =
            "Tiempo de secado estimado: ${l.tiempoEstimadoMin / 60}h ${l.tiempoEstimadoMin % 60}m"
        tvIntegridad.text = when (l.integridad) {
            "ok" -> "Datos verificados (firma HMAC-SHA256 válida)"
            "invalida" -> "ATENCIÓN: firma inválida, los datos podrían estar alterados"
            else -> "Datos sin firma de integridad"
        }
        tvActualizado.text = when {
            deCache -> "Último dato guardado en el teléfono (sin conexión)"
            l.antiguedadS != null -> "Lectura del dispositivo hace ${l.antiguedadS} s"
            else -> ""
        }
        aplicarActuador(swVentilador, "ventilador", l.ventilador)
        aplicarActuador(swCalefactor, "calefactor", l.calefactor)
    }

    /** Muestra el estado REAL del actuador; mientras hay un comando en curso respeta lo que pidió el usuario. */
    private fun aplicarActuador(sw: MaterialSwitch, nombre: String, real: Boolean) {
        if (!ApiConfig.ACTUADORES_HABILITADOS) return
        val pedido = esperando[nombre]
        if (pedido != null) {
            if (pedido.first == real || System.currentTimeMillis() > pedido.second) esperando.remove(nombre) else return
        }
        sw.isChecked = real
    }

    // ------------------------------------------------------------------ energía y sesión
    private fun ahorroEnergia(): Boolean {
        val i = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val nivel = i?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val escala = i?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val estado = i?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val cargando = estado == BatteryManager.BATTERY_STATUS_CHARGING || estado == BatteryManager.BATTERY_STATUS_FULL
        val porcentaje = if (nivel >= 0 && escala > 0) nivel * 100 / escala else -1
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return Politicas.ahorroEnergia(porcentaje, cargando, pm.isPowerSaveMode)
    }

    private fun cerrarSesion() {
        lifecycleScope.launch {
            repo.cerrarSesion()                       // borra cola y caché locales
            FirebaseAuth.getInstance().signOut()
            startActivity(Intent(this@MainActivity, LoginActivity::class.java))
            finish()
        }
    }
}
