REM You can use this batch file to run your API locally with your local SQLite database to  test and confirm your code is fully functional before moving to production in the web 

REM This batch file will work only if you have created and activated the Python virtual environment in a Terminal window

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000