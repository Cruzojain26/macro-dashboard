@echo off
rem Local fallback updater: refreshes data and pushes to GitHub (Pages redeploys).
cd /d "%~dp0"
set PY=C:\Users\HP_PC\AppData\Local\Programs\Python\Python313\python.exe
%PY% fetch_fred.py && %PY% fetch_markets.py && %PY% analyze.py
git add data/
git diff --cached --quiet || (git commit -m "local data refresh" && git push)
