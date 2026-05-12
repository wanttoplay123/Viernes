# Viernes AI

Asistente personal que vive en tu PC, observa lo que haces, aprende sin que le enseñes, ejecuta lo que le dices, y recuerda todo. 100% local, sin cloud, sin suscripciones.

## Requisitos

- Python 3.11+
- Ollama instalado (https://ollama.ai)
- Windows 10/11

## Instalación

```bash
# Clonar o descargar el proyecto
cd Viernes

# Crear entorno virtual
python -m venv env
env\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar dependencias adicionales de F5
pip install openai-whisper PyQt6 keyboard pyttsx3 pystray

# Instalar playwright (si usas F3)
playwright install chromium
```

## Modelos Ollama

```bash
# Modelo principal (F2-F4)
ollama pull llama3.2:3b
```

## Estructura

```
Viernes/
├── main.py              # Orquestador principal
├── activity_logger.py   # F1 - Logger de actividad
├── phase2_indexer.py    # F2 - Indexador de memoria
├── semantic_query.py    # F2 - Búsqueda semántica
├── friday_executor.py   # F3 - Ejecutor de acciones
├── action_bridge.py     # F3 - Puente JSON->acción
├── os_controller.py     # F3 - Control del OS
├── phase4_patterns.py   # F4 - Detección de patrones
├── voice.py             # F5 - Voz (STT/TTS)
├── systray.py           # F5 - Icono en bandeja
├── autostart.py         # F5 - Auto-inicio Windows
├── ollama_client.py     # Cliente Ollama
├── permissions.py       # Sistema de permisos
└── permissions.json    # Whitelist de permisos
```

## Uso

### Inicio rápido

```bash
# Iniciar todos los módulos
python main.py

# Iniciar solo logger
python main.py --modules logger

# Iniciar con intervalos custom
python main.py --modules logger indexer --indexer-interval 5
```

### Módulos individuales

```bash
# F1 - Logger de actividad
python activity_logger.py

# F2 - Indexar sesiones
python phase2_indexer.py --once

# F2 - Buscar en memoria
python query_events.py "qué estaba haciendo ayer"

# F3 - Ejecutar acción
python friday_executor.py "abre el bloc de notas"

# F4 - Detectar patrones
python phase4_patterns.py --min-occurrences 2

# F5 - Voz
python voice.py --listen           # Escuchar
python voice.py --speak "Hola"     # Hablar

# F5 - System tray
python systray.py

# F5 - Auto-inicio
python autostart.py --enable      # Habilitar
python autostart.py --status      # Ver estado
```

## Configuración

### Permisos

Edita `permissions.json` para configurar qué acciones puede ejecutar Viernes:

```json
{
  "allowed_apps": ["notepad.exe", "code.exe", "chrome.exe"],
  "allowed_folders": ["C:\\Users\\USUARIO\\Documentos"],
  "allowed_contacts": ["juan@email.com"]
}
```

## Estado

| Fase | Estado |
|------|--------|
| F1 - Logger | ✅ Completo |
| F2 - Memoria semántica | ✅ Completo |
| F3 - Control del OS | ✅ Completo |
| F4 - Patrones | ✅ Completo |
| F5 - Interfaz y voz | ✅ Completo |

## Troubleshooting

### Ollama no responde
```bash
ollama serve
ollama list
```

### Error de permisos
Ejecuta como administrador o verifica `permissions.json`

### Whisper no carga
```bash
pip install openai-whisper --upgrade
```