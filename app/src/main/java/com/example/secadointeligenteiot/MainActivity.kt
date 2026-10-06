package com.example.secadointeligenteiot

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.secadointeligenteiot.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection

class MainActivity : AppCompatActivity() {

    private lateinit var tvClima: TextView
    private lateinit var tvRecomendacion: TextView
    private lateinit var tvTiempoSecado: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvClima = findViewById(R.id.tvClima)
        tvRecomendacion = findViewById(R.id.tvRecomendacion)
        tvTiempoSecado = findViewById(R.id.tvTiempoSecado)

        fetchAwsIoTData()
    }

    private fun fetchAwsIoTData() {

        CoroutineScope(Dispatchers.IO).launch {
            try {

                val awsApiUrl = URL("https://c9mo8wujsj.execute-api.us-east-1.amazonaws.com/default/ObtenerClima")

                val connection = awsApiUrl.openConnection() as HttpsURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 5000
                connection.readTimeout = 5000

                if (connection.responseCode == HttpURLConnection.HTTP_OK) {
                    val reader = BufferedReader(InputStreamReader(connection.inputStream))
                    val response = reader.readText()
                    reader.close()

                    val jsonObject = JSONObject(response)
                    val temperatura = jsonObject.getInt("temperatura")
                    val humedad = jsonObject.getInt("humedad")
                    val horaOptima = jsonObject.getString("hora_optima")
                    val tiempoEstimado = jsonObject.getInt("tiempo_estimado_minutos")


                    withContext(Dispatchers.Main) {
                        tvClima.text = "Temperatura: $temperatura°C | Humedad: $humedad%"
                        tvRecomendacion.text = "Hora recomendada para tender: $horaOptima hrs"
                        tvTiempoSecado.text = "Tiempo de secado estimado: ${tiempoEstimado / 60}h ${tiempoEstimado % 60}m"
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    tvClima.text = "Error al conectar con el nodo IoT (AWS)"

                }
            }
        }
    }
}