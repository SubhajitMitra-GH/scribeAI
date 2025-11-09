# Start with a modern Python 3.12 image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# 1. Install ffmpeg
# This is the system dependency that whisper needs
RUN apt-get update && apt-get install -y ffmpeg

# 2. Install the SMALL CPU-only torch to prevent OOM errors
# This is the most important fix
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# 3. Manually install whisper
# It will see the small torch is already installed and use it
RUN pip install openai-whisper

# 4. Copy and install your other requirements
# (Make sure torch and whisper are DELETED from this file)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 5. Copy the rest of your app's code (app.py, etc.)
COPY . .

# 6. Set the command to run your server
# This tells Gunicorn to run the 'app' variable from the 'app.py' file
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]