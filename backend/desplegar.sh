#!/usr/bin/env bash
# Despliegue automático del backend en AWS Academy. Ejecutar en AWS CloudShell (región us-east-1):
#   git clone -b unidad3-comunicacion-segura https://github.com/Rincaz/SecadoTiempoRopa.git
#   cd SecadoTiempoRopa/backend && bash desplegar.sh
# Es repetible (idempotente). No crea roles IAM: usa el rol que ya tiene la Lambda (LabRole).
set -euo pipefail
API_ID="${API_ID:-c9mo8wujsj}"
FUNCION="${FUNCION:-ObtenerClima}"
TABLA="${TABLA:-DatosClima}"
DISPOSITIVOS="${DISPOSITIVOS:-RaspberryVirtual,RaspberrySecadora2}"
REGION="${AWS_REGION:-us-east-1}"
cd "$(dirname "$0")"

echo "==> 1/6 Claves de la tabla $TABLA"
read -r PK SK < <(aws dynamodb describe-table --table-name "$TABLA" --query 'Table.KeySchema' --output json |
  python3 -c "import json,sys; k=json.load(sys.stdin); print(next(x['AttributeName'] for x in k if x['KeyType']=='HASH'), next((x['AttributeName'] for x in k if x['KeyType']=='RANGE'), 'timestamp'))")
echo "    partition key=$PK  sort key=$SK"

echo "==> 2/6 Empaquetar y subir código de la Lambda $FUNCION"
python3 - <<'PY'
import zipfile
with zipfile.ZipFile("lambda.zip", "w", zipfile.ZIP_DEFLATED) as z:
    z.write("lambda_function.py")
PY
aws lambda update-function-code --function-name "$FUNCION" --zip-file fileb://lambda.zip >/dev/null
aws lambda wait function-updated --function-name "$FUNCION"

echo "==> 3/6 Variables de entorno (se conservan las existentes; HMAC_CLAVE se crea sólo si no existe)"
IOT_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text)
aws lambda get-function-configuration --function-name "$FUNCION" --query 'Environment.Variables' --output json > env_actual.json
TABLA="$TABLA" PK="$PK" SK="$SK" DISPOSITIVOS="$DISPOSITIVOS" IOT_ENDPOINT="$IOT_ENDPOINT" python3 - <<'PY'
import json, os, secrets
actual = json.load(open("env_actual.json")) or {}
actual.update({"TABLA": os.environ["TABLA"], "PK_NAME": os.environ["PK"], "SK_NAME": os.environ["SK"],
               "DISPOSITIVOS": os.environ["DISPOSITIVOS"], "IOT_ENDPOINT": os.environ["IOT_ENDPOINT"]})
actual.setdefault("HMAC_CLAVE", secrets.token_hex(32))
json.dump({"Variables": actual}, open("env.json", "w"))
PY
aws lambda update-function-configuration --function-name "$FUNCION" --handler lambda_function.lambda_handler \
  --runtime python3.12 --timeout 10 --environment file://env.json >/dev/null
aws lambda wait function-updated --function-name "$FUNCION"
rm -f env.json env_actual.json lambda.zip

echo "==> 4/6 Integración y rutas de la API $API_ID"
ARN=$(aws lambda get-function --function-name "$FUNCION" --query Configuration.FunctionArn --output text)
INTEG=$(aws apigatewayv2 get-integrations --api-id "$API_ID" --query "Items[?contains(IntegrationUri,'$FUNCION')].IntegrationId | [0]" --output text)
if [ -z "$INTEG" ] || [ "$INTEG" = "None" ]; then
  INTEG=$(aws apigatewayv2 create-integration --api-id "$API_ID" --integration-type AWS_PROXY \
    --integration-uri "$ARN" --payload-format-version 2.0 --query IntegrationId --output text)
else
  aws apigatewayv2 update-integration --api-id "$API_ID" --integration-id "$INTEG" --payload-format-version 2.0 >/dev/null
fi
for R in "GET /ObtenerClima" "GET /HistorialClima" "POST /ComandoSecadora"; do
  EXISTE=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='$R'].RouteId | [0]" --output text)
  if [ -z "$EXISTE" ] || [ "$EXISTE" = "None" ]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$R" --target "integrations/$INTEG" >/dev/null
    echo "    ruta creada: $R"
  else
    aws apigatewayv2 update-route --api-id "$API_ID" --route-id "$EXISTE" --target "integrations/$INTEG" >/dev/null
    echo "    ruta existente: $R"
  fi
done

echo "==> 5/6 Permiso de API Gateway para invocar la Lambda y publicación de la etapa"
CUENTA=$(aws sts get-caller-identity --query Account --output text)
aws lambda add-permission --function-name "$FUNCION" --statement-id "apigw-${API_ID}-todas" \
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${REGION}:${CUENTA}:${API_ID}/*/*/*" >/dev/null 2>&1 || true
AUTO=$(aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name default --query AutoDeploy --output text 2>/dev/null || echo None)
if [ "$AUTO" != "True" ]; then aws apigatewayv2 create-deployment --api-id "$API_ID" --stage-name default >/dev/null; fi
sleep 5

echo "==> 6/6 Prueba"
URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/default/ObtenerClima?dispositivo=RaspberryVirtual"
curl -s -w "\n   HTTP %{http_code}\n" "$URL"
echo
echo "Listo. Si ves JSON con temperatura/humedad, la app ya puede conectarse."
echo "Clave HMAC (para edge/config.json cuando uses el gateway):"
echo "  aws lambda get-function-configuration --function-name $FUNCION --query 'Environment.Variables.HMAC_CLAVE' --output text"
echo "Cuando todo funcione, protege la API con:  bash proteger_api.sh"
