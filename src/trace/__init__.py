from agents.tracing import set_trace_processors
from agents.tracing.processors import BatchTraceProcessor, ConsoleSpanExporter

BATCH_TRACE_PROCESSOR = BatchTraceProcessor(exporter=ConsoleSpanExporter())
set_trace_processors(processors=[BATCH_TRACE_PROCESSOR])
