import os

from crime_detector import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))
