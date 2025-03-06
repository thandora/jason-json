#!/usr/bin/env bash
# Exit on error
set -o errexit

# Add Microsoft repository for SQL Server ODBC Driver
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list

# Install SQL Server ODBC Driver and other dependencies
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

pip install -r requirements.txt