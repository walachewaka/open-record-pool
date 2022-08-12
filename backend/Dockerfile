# Set the base Docker image.
FROM python:3.10-slim-buster

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install build-essential -y

# Set the working directory in the container.
WORKDIR /app

# Make sure we can load local Python modules.
ENV PATH="${PATH}:/root/.local/bin"
ENV PYTHONPATH=.

# Copy the dependencies file inside the image.
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install flake8
RUN pip install -r requirements.txt

# Copy the source code to inside the image.
# We do this after the requirements step, so that we can benefit from multi-stage compilation speedup.
COPY aerich.ini ./
ADD migrations/ migrations/
ADD src/ src/

RUN flake8 --ignore=E501,F401,W391,E261,E402 .
# TODO: run black

# We load the music from the /music path:
VOLUME ["/music"]

EXPOSE 5000

# We need to specify the command to run inside the container in the docker-compose.yml file.
# See ../docker-compose.yml

