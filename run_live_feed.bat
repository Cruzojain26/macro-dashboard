@echo off
rem Live intraday quote feeder (exits instantly when no market is open).
cd /d "%~dp0"
"C:\Users\HP_PC\AppData\Local\Programs\Python\Python313\python.exe" live_feed.py >> live_feed_log.txt 2>&1
