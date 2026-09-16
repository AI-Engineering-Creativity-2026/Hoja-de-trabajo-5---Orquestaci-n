# HDT5 — Orquestación de agentes para Parachute S.A.

<p align="center">
  <img src="assets/a1b3ca08-2d66-4a54-947d-67325b9a1f93.png" alt="Imagen" width="600">
</p>

<h1 align="center">🎵🎵🎵 RECOMENDACIÓN MUSICAL 🎵🎵🎵</h1>

<p align="center">
  <a href="https://www.youtube.com/watch?v=UsbRoaH6y-Q">
    <img src="https://img.youtube.com/vi/UsbRoaH6y-Q/maxresdefault.jpg" alt="Recomendación musical" width="900">
  </a>
</p>

<p align="center">
  <img src="assets/a1b3ca08-2d66-4a54-947d-67325b9a1f93.png" alt="Imagen" width="360">
  <img src="assets/kyafeet.jpg" alt="Imagen" width="360">
  <img src="assets/jiyufeet.webp" alt="Imagen" width="360">
</p>

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
# Si ya levantaste PostgreSQL desde HDT4, reutiliza ese contenedor:
# docker start parachute-postgres
../ai-function-calls/.venv/bin/python hdt4/src/load_corpus.py --corpus data/Corpus_FAQs_Parachute_SA_2026.txt
python centralizada.py "Quiero saltar el 2026-09-20"
python jerarquica.py "¿Puedo agendar un salto el 2026-09-20?"
python descentralizada.py "¿Qué incluye una cita tándem?"
```

Para probar el mismo entorno virtual sin depender de que `python` global tenga las dependencias, también puedes ejecutar directamente `../ai-function-calls/.venv/bin/python centralizada.py ...`.

Se reutiliza el entorno virtual y PostgreSQL/pgvector de HDT4 cuando ya están instalados. Si no existe el contenedor, puede crearse con `docker compose -f hdt4/docker-compose.yml --env-file .env up -d`; si ya existe `parachute-postgres`, no ejecutes ese comando porque Docker reportará conflicto de nombre. Las FAQs de las tres arquitecturas llaman al mismo `search_knowledge_base` vectorial de HDT4; no se mantiene un buscador alternativo por coincidencia de palabras. La integración usa la documentación oficial de [Open-Meteo](https://open-meteo.com/).

Para Groq se usa `openai/gpt-oss-20b`, que está disponible en el entorno de HDT4. El código envía `include_reasoning=false` para separar el razonamiento de las llamadas a tools.

También se puede ejecutar sin argumento y escribir la consulta interactiva. Las fechas deben expresarse como `YYYY-MM-DD` para que el agente pueda validarlas de manera determinista.

Para abrir el chat multi-turno, ejecuta sin argumentos:

```bash
python centralizada.py
python jerarquica.py
python descentralizada.py
```

El historial se conserva durante la sesión; escribe `salir`, `exit` o `quit` para terminar. Con un argumento, el programa conserva el modo de consulta única.

## Entregables

- Diagramas Mermaid: `diagramas/*.mmd`.
- Respuestas razonadas: `respuestas_hdt5.pdf` y su fuente `respuestas_hdt5.md`.
- Pruebas unitarias para los umbrales: `tests/test_parachute.py`.
- Las citas aprobadas se registran en `data/citas.json` y quedan pendientes de confirmación del instructor.
- `probar_todos_casos.py` cubre todos los umbrales y validaciones; agrega `--live` para consultar las fechas reales disponibles.

## Nota de seguridad

La recomendación automática no reemplaza la decisión del instructor o del piloto. Cualquier condición insegura o dato meteorológico ausente bloquea la calendarización.

## Configuración completa paso a paso

### 1. Activar el entorno virtual

El proyecto reutiliza el entorno virtual de HDT4 para que ambas hojas de trabajo usen las mismas dependencias:

```bash
source ../ai-function-calls/.venv/bin/activate
pip install -r requirements.txt
```

Si el comando `python` no encuentra `dotenv` o `agents`, usa directamente:

```bash
../ai-function-calls/.venv/bin/python centralizada.py
```

### 2. Configurar las variables de entorno

Copia `.env.example` como `.env` y edítalo. La variable `GROQ_API_KEY` debe contener una clave de Groq que empiece con `gsk_`. No uses una clave de OpenAI en el campo de Groq y nunca subas el archivo `.env`.

Para evitar que una clave antigua exportada en la terminal tenga prioridad:

```bash
unset GROQ_API_KEY OPENAI_API_KEY
set -a
source .env
set +a
```

Una clave nueva dentro de la misma organización de Groq no reinicia el límite diario de tokens. Un error `429` con `tokens per day` requiere esperar al reinicio de cuota o utilizar una organización con disponibilidad.

### 3. Preparar PostgreSQL y pgvector

HDT4 almacena los embeddings de las FAQs en PostgreSQL. Si ya existe el contenedor `parachute-postgres`, está activo y saludable, no vuelvas a ejecutar Compose: simplemente reutilízalo y carga el corpus:

```bash
docker start parachute-postgres
../ai-function-calls/.venv/bin/python hdt4/src/load_corpus.py \
  --corpus data/Corpus_FAQs_Parachute_SA_2026.txt
```

Si el contenedor no existe, créalo una sola vez:

```bash
docker compose --env-file .env -f hdt4/docker-compose.yml up -d
```

El error `Conflict. The container name /parachute-postgres is already in use` significa que el contenedor de HDT4 ya existe; no significa que el proyecto esté roto. En ese caso, usa el primer procedimiento.

## Flujo interno de una consulta

Cada archivo principal construye sus agentes, pero importa las mismas herramientas desde `shared/parachute.py`.

1. El agente recibe la consulta del usuario.
2. Las preguntas sociales (`hola`, `cómo estás`, etc.) usan las respuestas conversacionales originales de HDT4.
3. Las preguntas sobre el evento pasan por el flujo `run_agent_turn` original de HDT4.
4. HDT4 divide preguntas compuestas, llama `search_knowledge_base`, consulta PostgreSQL/pgvector y redacta únicamente con la evidencia encontrada.
5. Las solicitudes con fecha se validan antes de continuar. Se rechazan fechas pasadas y fechas desde el día 16 en adelante, porque Open-Meteo solo permite los próximos 16 días contando hoy.
6. `fetch_weather()` llama a Open-Meteo con las coordenadas del aeródromo y las variables diarias requeridas.
7. `evaluate_weather()` aplica los umbrales del enunciado. Una sola condición crítica vuelve el resultado `NO SEGURO / PROHIBIDO`.
8. `schedule_tool()` consulta el clima nuevamente como última barrera. Nunca confía únicamente en una respuesta del modelo.
9. Una cita solo se escribe en `data/citas.json` si es `IDEAL` o `MARGINAL`. Se guarda como tentativa con estado `pending_instructor_confirmation`.

## Arquitecturas implementadas

### Centralizada

`SupervisorCentral` es el único coordinador. Sus workers son `WeatherWorker`, `FAQWorker` y `CalendarWorker`. El supervisor accede a ellos mediante `as_tool()`. La ruta típica de una cita es:

```text
SupervisorCentral → WeatherWorker → CalendarWorker
                 └→ FAQWorker (preguntas del evento)
```

### Jerárquica

`RootManager` recibe la solicitud y la entrega a `WeatherManager`, `FAQManager` o `CalendarManager`. Cada manager utiliza su worker especializado mediante `as_tool()`. Esto representa dos niveles de coordinación: manager raíz y manager especializado.

### Descentralizada

`IntakeAgent`, `WeatherAgent`, `FAQAgent` y `CalendarAgent` son agentes pares. No existe un supervisor central. La transferencia se realiza con `handoff()`, por ejemplo:

```text
IntakeAgent ⇄ WeatherAgent ⇄ CalendarAgent
     └──────⇄ FAQAgent
```

Los diagramas completos se encuentran en `diagramas/` y pueden visualizarse como Mermaid.

## Comandos de ejecución

Chat interactivo:

```bash
python centralizada.py
python jerarquica.py
python descentralizada.py
```

Consulta individual:

```bash
python centralizada.py "¿Cuál es el peso máximo?"
python jerarquica.py "Quiero calendarizar una cita el 2026-09-20"
python descentralizada.py "¿Dónde se ubica la zona de salto?"
```

Una continuación como `2026-09-17 para esta fecha` se envía directamente al flujo de clima y calendarización. Es necesario escribir la fecha como `YYYY-MM-DD`.

## Pruebas

Las pruebas verifican los límites ideales, marginales y prohibidos, validación de fechas, bloqueo de citas inseguras, respuestas FAQ y frases naturales de reserva:

```bash
../ai-function-calls/.venv/bin/python -m unittest discover -s tests -v
```

Para probar fechas reales disponibles:

```bash
python probar_todos_casos.py --live
```

El script de pruebas en vivo consume la API de Open-Meteo y puede tardar más que las pruebas unitarias.
