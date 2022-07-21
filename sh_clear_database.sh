#!/bin/bash
echo "We will now erase your PostgreSQL database."
read -p "Are you sure? y/n: " -n 1 -r
echo # (optional) move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]
then
    docker-compose down --volumes
fi

