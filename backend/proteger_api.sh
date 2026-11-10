#!/usr/bin/env bash
# Exige el token de Firebase en las rutas de la API (JWT authorizer). Ejecutar DESPUÉS de comprobar que todo funciona.
set -euo pipefail
API_ID="${API_ID:-c9mo8wujsj}"
cd "$(dirname "$0")"
PROYECTO=$(python3 -c "import json; print(json.load(open('../app/google-services.json'))['project_info']['project_id'])")
AUTH=$(aws apigatewayv2 get-authorizers --api-id "$API_ID" --query "Items[?Name=='FirebaseJWT'].AuthorizerId | [0]" --output text)
if [ -z "$AUTH" ] || [ "$AUTH" = "None" ]; then
  AUTH=$(aws apigatewayv2 create-authorizer --api-id "$API_ID" --name FirebaseJWT --authorizer-type JWT \
    --identity-source '$request.header.Authorization' \
    --jwt-configuration "Audience=$PROYECTO,Issuer=https://securetoken.google.com/$PROYECTO" \
    --query AuthorizerId --output text)
fi
for R in "GET /ObtenerClima" "GET /HistorialClima" "POST /ComandoSecadora"; do
  ID=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='$R'].RouteId | [0]" --output text)
  aws apigatewayv2 update-route --api-id "$API_ID" --route-id "$ID" --authorization-type JWT --authorizer-id "$AUTH" >/dev/null
  echo "protegida: $R"
done
echo "Prueba sin token (debe dar 401):"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "https://${API_ID}.execute-api.us-east-1.amazonaws.com/default/ObtenerClima"
