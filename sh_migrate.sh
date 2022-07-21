#!/bin/bash
# Run the database migration
# First make sure to start Docker Compose
# docker-compose up -d --build

TORTOISE_CONFIG=src.database.config.TORTOISE_ORM

echo init:
docker-compose exec backend \
    aerich init --tortoise-orm ${TORTOISE_CONFIG}

echo init-db:
docker-compose exec backend \
    aerich init-db

echo upgrade:
docker-compose exec backend \
    aerich upgrade

