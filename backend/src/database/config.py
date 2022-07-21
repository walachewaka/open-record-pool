import os

# Configuration option for the Tortoise ORM.
# We specify here the Python module for our models,
# and the URL of our database.

TORTOISE_ORM = {
    "connections": {"default": os.environ.get("DATABASE_URL")},
    "apps": {
        "models": {
            "models": [
                "src.database.models",
                "aerich.models"
            ],
            "default_connection": "default"
        }
    }
}

