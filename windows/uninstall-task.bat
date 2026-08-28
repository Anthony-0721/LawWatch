@echo off
schtasks /delete /f /tn "LawWatch Monitor"
echo Task removed. config.json and data were kept.
