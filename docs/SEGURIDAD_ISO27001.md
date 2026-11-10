# Mapa de controles ISO/IEC 27001:2022 (Anexo A) / 27002 aplicados

| Control | Medida implementada | Evidencia |
|---|---|---|
| A.5.15 / A.8.2 Control de acceso, privilegios | Login Firebase; API Gateway con JWT authorizer; política IoT mínima por *thing* | `DESPLIEGUE_AWS_ACADEMY.md` §4, `iot_policy_dispositivo.json` |
| A.5.17 / A.8.5 Autenticación segura | Token de Firebase por petición, renovación automática; certificado X.509 por dispositivo | `ApiClient.kt`, `gateway.py` |
| A.8.24 Criptografía | TLS 1.2+ en HTTPS y MQTT (puerto 8883); AES‑256‑GCM para datos locales; HMAC‑SHA256 / SHA‑256 para integridad | `CajaFuerte.kt`, `protocolo.py`, `Hash.kt` |
| A.8.20 / A.8.21 Seguridad de redes | Sin tráfico en claro (`cleartextTrafficPermitted=false`); *throttling* en API | `network_security_config.xml` |
| A.8.26 Requisitos de seguridad de aplicaciones | Validación de entradas en Lambda (lista blanca de dispositivos, actuadores y acciones; formato de `id`) | `lambda_function.py` |
| A.8.15 Registro | Auditoría de cada comando (uid, dispositivo, acción) en CloudWatch | `comando_secadora()` |
| A.8.10 / A.5.34 Privacidad y datos personales | Minimización (la API devuelve sólo lo necesario; el correo no se registra), TTL 30 días, borrado local al cerrar sesión, sin copias de seguridad | `iot_regla.sql`, `LocalStore.borrarTodo()`, `backup_rules.xml` |
| A.8.13 / A.5.30 Continuidad | Caché, cola de comandos, buffer del gateway, modo seguro | `PLAN_CONTINGENCIA.md` |
| A.8.9 / A.8.8 Configuración y vulnerabilidades | Dependencias fijadas; secretos fuera del repositorio (`.gitignore` del edge); clave HMAC en variable de entorno | `edge/.gitignore` |
| A.8.16 Monitoreo | Campo `en_linea`, `antiguedad_s` e `integridad` visibles en la app | `MainActivity.kt` |

## Limitaciones conocidas (declararlas honestamente en la presentación)
- AWS Academy no permite crear roles IAM ni Cognito; por eso la autenticación de la app usa Firebase.
- La clave HMAC es simétrica y vive en variable de entorno de la Lambda (en producción: Secrets Manager / KMS).
- No se implementó *certificate pinning* (los certificados de Amazon rotan; se recomienda pinnear la CA raíz).
- El archivo `google-services.json` y la URL de la API están en el repositorio público: la API ya exige token, pero
  conviene restringir la API key de Firebase por *package name* y huella SHA‑1 en la consola de Google Cloud.
