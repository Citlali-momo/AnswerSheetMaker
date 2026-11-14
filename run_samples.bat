@echo off
rem Generate two demo answer sheets (color/bubble and bw/table with figures).
rem Usage: double-click, or run  run_samples.bat  in cmd.
rem Titles and other text are read from config.json (UTF-8), so no Chinese
rem is passed through the command line here.
cd /d %~dp0

python demo_figure.py figs\cube.png

python answer_sheet.py -c config.json ^
  -o out\answer_color_bubble.pdf --preview out\answer_color_bubble.png --check

python answer_sheet.py -c config.json --choice-mode table --color-mode bw ^
  --image 15=figs\cube.png --image 17=figs\cube.png ^
  -o out\answer_bw_table.pdf --preview out\answer_bw_table.png --check

echo.
echo Done. Files are in the "out" folder.
pause
