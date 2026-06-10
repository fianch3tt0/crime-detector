import os
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql://localhost/crimedetector")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SODA_ENDPOINT = os.environ.get(
        "SODA_ENDPOINT",
        "https://data.fortworthtexas.gov/resource/k6ic-7kp7.json",
    )
    SODA_APP_TOKEN = os.environ.get("SODA_APP_TOKEN", "")
    SODA_PAGE_SIZE = 1000
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300
    CLUSTER_THRESHOLD = 500


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    CACHE_TYPE = "NullCache"
    # Overridden per-test by pytest-postgresql fixture
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://localhost/crimedetector_test"
    )


class ProductionConfig(BaseConfig):
    CACHE_TYPE = os.environ.get("CACHE_TYPE", "SimpleCache")


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
