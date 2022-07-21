"""
Function to register the tortoise database ORM into our FastAPI app.
"""
from typing import Optional
from tortoise import Tortoise


def register_tortoise(
    app,
    config: Optional[dict] = None,
    generate_schemas: bool = False,
) -> None:
    """
    Function to register the tortoise database ORM into our FastAPI app.
    """
    @app.on_event("startup")
    async def init_orm():
        await Tortoise.init(config=config)
        if generate_schemas:
            await Tortoise.generate_schemas()

    @app.on_event("shutdown")
    async def close_orm():
        await Tortoise.close_connections()

