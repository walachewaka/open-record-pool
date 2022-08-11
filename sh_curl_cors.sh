#!/bin/bash
# Do a cURL query to check if we use CORS.

FRONTEND=http://localhost:8088
BACKEND=http://localhost:5000

curl -H "Origin: ${FRONTEND}" --verbose ${BACKEND}/version && echo

