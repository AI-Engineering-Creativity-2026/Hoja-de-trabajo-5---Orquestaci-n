# HDT5 — Orquestación de agentes para Parachute S.A.

Implementación del mismo asistente de calendarización de saltos con tres arquitecturas:

- `centralizada.py`: un supervisor y workers expuestos como tools mediante `as_tool()`.
- `jerarquica.py`: manager raíz → manager de clima/FAQ → workers.
- `descentralizada.py`: agentes independientes que se delegan con `handoffs`.

La lógica de negocio y la integración con Open-Meteo viven en `shared/parachute.py` y no se duplican entre arquitecturas.

## Instalación y ejecución

```bash
source ../ai-function-calls/.venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edita .env y coloca tu GROQ_API_KEY de HDT4
python centralizada.py "Quiero saltar el 2026-09-20"
python jerarquica.py "¿Puedo agendar un salto el 2026-09-20?"
python descentralizada.py "¿Qué incluye una cita tándem?"
```

Para probar el mismo entorno virtual sin depender de que `python` global tenga las dependencias, también puedes ejecutar directamente `../ai-function-calls/.venv/bin/python centralizada.py ...`.

Se reutiliza el entorno virtual de HDT4 (`../ai-function-calls/.venv`) y se incluye una copia del corpus de FAQs en `data/Corpus_FAQs_Parachute_SA_2026.txt`; la ruta de HDT4 queda como respaldo local. La integración usa la documentación oficial de [Open-Meteo](https://open-meteo.com/).

Para Groq se usa `openai/gpt-oss-20b`, que está disponible en el entorno de HDT4. El código envía `include_reasoning=false` para separar el razonamiento de las llamadas a tools.

También se puede ejecutar sin argumento y escribir la consulta interactiva. Las fechas deben expresarse como `YYYY-MM-DD` para que el agente pueda validarlas de manera determinista.

## Entregables

- Diagramas Mermaid: `diagramas/*.mmd`.
- Respuestas razonadas: `respuestas_hdt5.pdf` y su fuente `respuestas_hdt5.md`.
- Pruebas unitarias para los umbrales: `tests/test_parachute.py`.
- Las citas aprobadas se registran en `data/citas.json` y quedan pendientes de confirmación del instructor.
- `probar_todos_casos.py` cubre todos los umbrales y validaciones; agrega `--live` para consultar las fechas reales disponibles.

## Nota de seguridad

La recomendación automática no reemplaza la decisión del instructor o del piloto. Cualquier condición insegura o dato meteorológico ausente bloquea la calendarización.
