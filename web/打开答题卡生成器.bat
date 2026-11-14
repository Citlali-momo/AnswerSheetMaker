@echo off
setlocal
cd /d "%~dp0"

rem Use whatever browser this machine has. No install needed.
set "EDGE1=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set "EDGE2=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
set "CHROME1=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "CHROME2=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set "IE=C:\Program Files\Internet Explorer\iexplore.exe"

if exist "%EDGE1%" ( start "" "%EDGE1%" "%~dp0answer_sheet.html" & goto done )
if exist "%EDGE2%" ( start "" "%EDGE2%" "%~dp0answer_sheet.html" & goto done )
if exist "%CHROME1%" ( start "" "%CHROME1%" "%~dp0answer_sheet.html" & goto done )
if exist "%CHROME2%" ( start "" "%CHROME2%" "%~dp0answer_sheet.html" & goto done )

rem Fallback: let Windows decide which program opens the html file
start "" "%~dp0answer_sheet.html"
goto done

:done
endlocal
