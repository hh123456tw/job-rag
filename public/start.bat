@echo off
rem Double-click to start. Defaults: the sample corpus and models\ next to this file.
rem To use your own data, set the variables before running (see README):
rem   set JOB_RAG_CORPUS=<folder with your .md files>
rem   set JOB_RAG_MODELS=<folder with the embedding models>
rem Phone mode: start.bat phone  (listens on the LAN so a phone on the same Wi-Fi can open it; default is this computer only).
rem Switches: set JOB_RAG_DETECT=0 or JOB_RAG_DEDUPE=0 to turn a feature off.
chcp 65001 >nul
cd /d "%~dp0"
if not defined JOB_RAG_CORPUS set "JOB_RAG_CORPUS=%~dp0sample_corpus"
if not defined JOB_RAG_MODELS set "JOB_RAG_MODELS=%~dp0models"
if not defined JOB_RAG_PORT set "JOB_RAG_PORT=5000"
if /i "%~1"=="phone" set "JOB_RAG_HOST=0.0.0.0"
start "" "http://127.0.0.1:%JOB_RAG_PORT%"
python -X utf8 app.py
pause
