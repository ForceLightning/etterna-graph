@echo off

pyinstaller pyinstaller.spec
move dist\main\main.exe EtternaGraph.exe
