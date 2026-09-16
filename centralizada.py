"""Arquitectura centralizada: un supervisor coordina todos los workers."""
import sys
from agents import Agent, function_tool
from shared.parachute import agent_model, agent_model_settings, faq_tool, run_agent, schedule_tool, weather_tool

MODEL = agent_model()
SETTINGS = agent_model_settings()
WEATHER_TOOL, FAQ_TOOL, SCHEDULE_TOOL = function_tool(weather_tool), function_tool(faq_tool), function_tool(schedule_tool)
weather_worker = Agent(name="WeatherWorker", instructions="Usa weather_tool para consultar y evaluar una fecha. Nunca inventes datos.", tools=[WEATHER_TOOL], model=MODEL, model_settings=SETTINGS)
faq_worker = Agent(name="FAQWorker", instructions="Responde exclusivamente usando faq_tool. Sé claro y breve.", tools=[FAQ_TOOL], model=MODEL, model_settings=SETTINGS)
calendar_worker = Agent(name="CalendarWorker", instructions="Usa schedule_tool para que la propia integración vuelva a consultar el clima. Nunca inventes ni reutilices un reporte.", tools=[SCHEDULE_TOOL], model=MODEL, model_settings=SETTINGS)
supervisor = Agent(
    name="SupervisorCentral",
    instructions=("Eres el único supervisor de Parachute S.A. Decide qué worker usar. "
                  "Para una cita, consulta clima antes de aceptar; nunca autorices si el reporte dice NO SEGURO. "
                  "Si el usuario desea calendarizar, llama primero a WeatherWorker y después a CalendarWorker con el reporte exacto. "
                  "Nunca escribas APTO si la decisión es NO SEGURO / PROHIBIDO. Nunca digas confirmada: la cita solo es tentativa si CalendarWorker devuelve scheduled=true; si devuelve error, informa que no se calendarizó."),
    model=MODEL, model_settings=SETTINGS,
    tools=[weather_worker.as_tool(tool_name="consultar_clima", tool_description="Consulta clima y aptitud para una fecha."),
           faq_worker.as_tool(tool_name="consultar_faq", tool_description="Consulta las preguntas frecuentes."),
           calendar_worker.as_tool(tool_name="calendarizar_cita", tool_description="Calendariza una cita con un reporte meteorológico aprobado.")],
)

if __name__ == "__main__":
    print(run_agent(supervisor, " ".join(sys.argv[1:]) or input("Consulta: ")))
