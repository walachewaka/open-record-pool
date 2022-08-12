"""
Main entry point of our backend service.
"""
import os
from typing import List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise import Tortoise

from src.database.register import register_tortoise
from src.database.config import TORTOISE_ORM

# enable schemas to read relationship between models
Tortoise.init_models(["src.database.models"], "models")

# Imports from src.routes must be after 'Tortoise.init_models'
# See https://stackoverflow.com/questions/65531387/tortoise-orm-for-python-no-returns-relations-of-entities-pyndantic-fastapi

from src.routes import notes
from src.routes import users
from src.extract import musicfiles

__version__ = '0.1.0-snapshot'
app_name = 'open-record-pool-backend'

app = FastAPI()


def parse_allowed_origins() -> List[str]:
    """
    Get the env var for the allowed origins:
    split this into a list of multiple allowed origins.
    Example:
    ALLOW_ORIGINS=http://localhost:8088,http://192.168.0.1:8088
    """
    allow_origins = os.environ.get("ALLOW_ORIGINS", "http://localhost:8088")
    ret = allow_origins.split(",")
    ret.append("http://localhost:8088")
    # Remove duplicates, if any:
    ret = list(set(ret))
    return ret


# Setup CORS:
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
app.include_router(notes.router)

# Setup the database:
register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False)


# Setup the endpoints:
@app.get("/")
def home():
    return f"This is {app_name} {__version__}"


@app.get("/music")
async def music():
    # Asynchronously load the informations from the music files:
    # TODO: Move this to a background task that is done only once.
    all_info = await musicfiles.list_all_music_files_info()
    return all_info


@app.get("/ping")
def ping():
    return {"ping": "pong!"}


@app.get("/version")
def version():
    return {"app": app_name, "version": __version__}

