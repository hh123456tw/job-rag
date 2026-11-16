@echo off
rem Double-click to start. Edit the paths below, or set the variables before running.
rem Switches: set JOB_RAG_DETECT=0 or JOB_RAG_DEDUPE=0 to turn a feature off.
chcp 65001 >nul
cd /d "%~dp0"
if not defined JOB_RAG_CORPUS set "JOB_RAG_CORPUS=C:\claude\aipe04期末\履歷\廠商深查"
if not defined JOB_RAG_MODELS set "JOB_RAG_MODELS=C:\claude\aipe04期末\job-rag\models"
if not defined JOB_RAG_PORT set "JOB_RAG_PORT=5000"
start "" "http://127.0.0.1:%JOB_RAG_PORT%"
python -X utf8 app.py
pause
