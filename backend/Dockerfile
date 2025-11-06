# Start with a modern Python 3.12 image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# --- This is the most important part ---
# Install ffmpeg from the system's package manager
RUN apt-get update && apt-get install -y ffmpeg

# Copy your requirements file first and install packages
# This is cached, so it's faster on future builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now, copy the rest of your application code
COPY . .

# Set the command to run your server (Gunicorn)
# It will listen on port 10000, which Render expects
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]