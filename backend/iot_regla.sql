-- Regla de AWS IoT Core -> acción "DynamoDBv2" (inserta cada campo como columna) en la tabla DatosClima.
-- WHERE: descarta mensajes cuyo campo "dispositivo" no coincide con el topic (suplantación entre dispositivos).
-- expira: atributo TTL (30 días) -> los datos no se conservan indefinidamente (minimización, ISO 27001 A.8.10).
SELECT *, timestamp() AS timestamp, floor(timestamp() / 1000) + 2592000 AS expira
FROM 'secadora/+/telemetria'
WHERE dispositivo = topic(2)
