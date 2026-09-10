"""
dba.connection — Database connection configuration.
 
Reads from domain.json's db_schema block when available. Falls back to
environment variables when no db_schema exists (standalone usage).
 
Connection strings are built in ODBC format for pyodbc. Credentials
never appear in summary() output.
"""
 
from __future__ import annotations
 
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional