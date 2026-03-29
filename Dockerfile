# Dockerfile para Review Capture Assist
# Nota: Orientado a desarrollo, builds y tareas de procesamiento posterior.
# La ejecución de la GUI requiere configuración adicional de X11/Wayland en el host.

FROM python:3.10-slim

# Instalar dependencias de sistema para Audio y Qt
RUN apt-get update && apt-get install -y \
    libasound2-dev \
    libportaudio2 \
    libgl1-mesa-glx \
    libxkbcommon-x11-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xinput0 \
    libxcb-xfixes0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Comando por defecto (útil para tests o procesamiento)
CMD ["python", "-m", "unittest", "discover", "tests"]
