import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "nas_backend")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret")

        # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  
    JWT_TOKEN_LOCATION = ["headers"]  
    JWT_HEADER_NAME = "Authorization"  
    JWT_HEADER_TYPE = "Bearer"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)