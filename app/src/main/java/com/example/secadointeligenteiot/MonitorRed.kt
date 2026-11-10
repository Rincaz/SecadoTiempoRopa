package com.example.secadointeligenteiot

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities

/**
 * Avisa cuando vuelve/se pierde la red: así la app reconecta de inmediato en lugar de consultar
 * a ciegas cada pocos segundos (reconexión automática 3.1.1.3 + ahorro de batería 3.1.3.10).
 * registerDefaultNetworkCallback exige API 24 (= minSdk).
 */
class MonitorRed(contexto: Context, private val alCambiar: (Boolean) -> Unit) {
    private val cm = contexto.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private var registrado = false

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = alCambiar(true)
        override fun onLost(network: Network) = alCambiar(false)
    }

    fun hayRed(): Boolean {
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    fun iniciar() {
        if (!registrado) {
            cm.registerDefaultNetworkCallback(callback)
            registrado = true
        }
    }

    fun detener() {
        if (registrado) {
            cm.unregisterNetworkCallback(callback)
            registrado = false
        }
    }
}
