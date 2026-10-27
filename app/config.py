"""Settings read from environment variables, with defaults for running on the host.

Inside Docker Compose, MONGO_URI is set to mongodb://mongo:27017 (see docker-compose.yml).
"""
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "tracking")
