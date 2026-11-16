@echo off
rem Double-click to share the app through an ngrok https address (for a phone or an interviewer).
rem Listens on this laptop only (127.0.0.1); ngrok forwards to it. The access code is random unless JOB_RAG_ACCESS_CODE is already set.
rem Close this window (or press Ctrl+C) to stop both the app and ngrok. Details: README, section "Public link".
chcp 65001 >nul
cd /d "%~dp0"
if not defined JOB_RAG_CORPUS set "JOB_RAG_CORPUS=C:\claude\aipe04期末\履歷\廠商深查"
if not defined JOB_RAG_MODELS set "JOB_RAG_MODELS=C:\claude\aipe04期末\job-rag\models"
if not defined JOB_RAG_PORT set "JOB_RAG_PORT=5000"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_public.ps1"
pause
