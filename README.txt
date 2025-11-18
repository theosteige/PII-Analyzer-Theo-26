*** How to run this project ***

1. Create python virtual environment in terminal (for mac, python -m venv (name of venv))
    - if this does not work, you might have a different python version. try python3 or whatever version you have
2. Activate the virtual environment (source (name of venv)/bin/activate)
3. Install dependencies (paste each in terminal: 
    pip install Flask; pip install presidio_analyzer; pip install presidio_anonymizer; 
    pip install flask_cors; python -m spacy download en_core_web_lg) - note, the spacy download might take a while
4. cd to the project folder containing server.py (cd presidio_analyzer-2.2.360-py3-none-any)
5. To run, in terminal, type python server.py
6. This should start the server, click on the local address to open the webpage
7. Type anything into the input box, debugging statements are printed to console if needed
