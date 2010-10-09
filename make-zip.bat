set REV=081
if exist ".\io_smd_tools-%REV%.zip" del ".\io_smd_tools-%REV%.zip"
7za a -tzip io_smd_tools-%REV%.zip io_smd_tools.py

