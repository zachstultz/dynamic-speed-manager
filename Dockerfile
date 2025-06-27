# Use a specific version of the Python image
FROM python:3.13.2-slim-bookworm

# Set the working directory to /app
WORKDIR /app

# Create a new user called "appuser"
RUN useradd -m appuser

# Set the default environment variables
ARG PUID=1000
ARG PGID=1000

# To avoid partial output in logs
ENV PYTHONUNBUFFERED=1

# Set ownership to appuser and switch to "appuser"
RUN groupmod -o -g "$PGID" appuser && usermod -o -u "$PUID" appuser

# Allow users to specify UMASK (default value is 022)
ENV UMASK=022
RUN umask "$UMASK"

# Copy the current directory contents into the container at /app
COPY --chown=appuser:appuser . .

# Install necessary packages and requirements for the main script
RUN apt-get update
RUN apt-get install -y tzdata
RUN pip3 install --no-cache-dir -r requirements.txt

# Remove unnecessary packages and clean up
RUN apt-get autoremove -y
RUN rm -rf /var/lib/apt/lists/*

# Switch to "appuser"
USER appuser

# Run the addon script in the background and redirect the output to a log file, then run the main script in the foreground.
CMD python3 -u dynamic_speed_manager.py