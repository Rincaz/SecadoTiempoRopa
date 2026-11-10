# Despliegue en AWS Academy (Learner Lab)

> Restricciones del Learner Lab que condicionan el diseño: sólo existe el rol **LabRole** (no se pueden
> crear roles IAM) y las credenciales temporales cambian en cada sesión. Por eso **la app nunca usa
> credenciales AWS**: habla con API Gateway y se autentica con su token de **Firebase Auth**.
> Región usada: `us-east-1`.

## Atajo: despliegue automático con CloudShell
En la consola de AWS abre **CloudShell** (icono `>_` arriba) y ejecuta:
```bash
git clone -b unidad3-comunicacion-segura https://github.com/Rincaz/SecadoTiempoRopa.git
cd SecadoTiempoRopa/backend && bash desplegar.sh      # Lambda + variables + rutas + prueba
bash proteger_api.sh                                  # después de comprobar que funciona: exige token Firebase
```
`desplegar.sh` detecta solo las claves de tu tabla, conserva las variables que ya tenías y es repetible.
Los pasos manuales de abajo hacen lo mismo y sirven como referencia.

## 1. DynamoDB
Tabla `DatosClima`. Claves esperadas por la Lambda (ajuste `PK_NAME`/`SK_NAME` si la suya es distinta):
- Partition key `dispositivo` (String) · Sort key `timestamp` (Number)
- Activar **TTL** sobre el atributo `expira`.

## 2. IoT Core
1. *Manage → Things*: crear un thing por equipo (`RaspberryVirtual`, `RaspberrySecadora2`) con certificado
   auto-generado. Descargar certificado, clave privada y `AmazonRootCA1.pem` → `edge/certs/` (¡nunca al repositorio!).
2. *Security → Policies*: crear `PoliticaSecadora` con `iot_policy_dispositivo.json` (reemplazar `CUENTA_AWS`)
   y asociarla a cada certificado. El thing sólo puede publicar/recibir en **sus** topics (mínimo privilegio).
3. *Message routing → Rules*: crear regla con el SQL de `iot_regla.sql`; acción **DynamoDBv2** → tabla
   `DatosClima`, rol `LabRole`.
4. Copiar el *Device data endpoint* (Settings) → `edge/config.json` y variable `IOT_ENDPOINT`.

## 3. Lambda
Reemplazar el código de la función `ObtenerClima` por `lambda_function.py` (runtime Python 3.12, rol `LabRole`,
timeout 10 s). Variables de entorno:

| Variable | Valor |
|---|---|
| `TABLA` | `DatosClima` |
| `PK_NAME` / `SK_NAME` | `dispositivo` / `timestamp` |
| `HMAC_CLAVE` | clave aleatoria larga (misma que `hmac_clave` del edge): `openssl rand -hex 32` |
| `DISPOSITIVOS` | `RaspberryVirtual,RaspberrySecadora2` |
| `IOT_ENDPOINT` | endpoint del paso 2.4 |

## 4. API Gateway (HTTP API existente)
1. Rutas → crear `GET /HistorialClima` y `POST /ComandoSecadora`; las 3 rutas (`GET /ObtenerClima` incluida)
   integradas con la misma Lambda.
2. *Authorization → Manage authorizers → Create → JWT*:
   - Issuer: `https://securetoken.google.com/secadorinteligenteiot`
   - Audience: `secadorinteligenteiot`
   - Identity source: `$request.header.Authorization`
3. Adjuntar ese authorizer a las 3 rutas. Con esto la API deja de ser pública.
4. *Throttling* de la etapa `default`: p. ej. 10 req/s, burst 20 (protege contra abuso y costos).

## 5. Pruebas rápidas
```bash
curl -i https://<api>/default/ObtenerClima                       # debe dar 401 (sin token)
curl -i -H "Authorization: Bearer <ID_TOKEN_FIREBASE>" "https://<api>/default/ObtenerClima?dispositivo=RaspberryVirtual"
```
El campo `integridad` debe ser `"ok"`; si alguien altera un registro en DynamoDB pasa a `"invalida"`.
Los comandos se pueden seguir en *IoT Core → MQTT test client* suscribiéndose a `secadora/#`.

## 6. Tareas recomendadas al iniciar cada sesión del lab
El Learner Lab apaga recursos entre sesiones: verifique que la VM tenga hora correcta
(`timedatectl`; los comandos caducan a los 120 s) y que el script del edge esté corriendo.
