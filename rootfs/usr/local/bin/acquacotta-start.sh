#!/bin/bash
exec gunicorn --bind 127.0.0.1:5000 --workers 2 --access-logfile - --error-logfile - app:app
