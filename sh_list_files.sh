#!/bin/bash
CONTAINER_ID=$(docker ps -aqf "name=frontend")
TARFILE=/tmp/suspect_container.tar

docker export ${CONTAINER_ID} > ${TARFILE} && vim ${TARFILE}

