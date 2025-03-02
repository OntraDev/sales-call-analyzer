#!/bin/bash
# Make sure the script has execute permissions
# chmod +x build.sh

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations if needed
python migrate_db.py

# Make the directory for database if it doesn't exist
mkdir -p instance
