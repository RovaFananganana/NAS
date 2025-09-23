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
    
    # Connection NAS
    SMB_USERNAME = os.getenv("SMB_USERNAME", "gestion")
    SMB_PASSWORD = os.getenv("SMB_PASSWORD", "Aeronav99")
    SMB_SERVER_IP = os.getenv("SMB_SERVER_IP", "10.61.17.33")
    SMB_SERVER_NAME = os.getenv("SMB_SERVER_NAME", "SERVER")
    SMB_SHARED_FOLDER = os.getenv("SMB_SHARED_FOLDER", "NAS")
    SMB_CLIENT_NAME = os.getenv("SMB_CLIENT_NAME", "admin")
    SMB_DOMAIN = os.getenv("SMB_DOMAIN", "")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret")

        # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  
    JWT_TOKEN_LOCATION = ["headers"]  
    JWT_HEADER_NAME = "Authorization"  
    JWT_HEADER_TYPE = "Bearer"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    # Performance Monitoring Configuration
    SLOW_QUERY_THRESHOLD_MS = float(os.getenv("SLOW_QUERY_THRESHOLD_MS", "100"))
    PERMISSION_QUERY_THRESHOLD_MS = float(os.getenv("PERMISSION_QUERY_THRESHOLD_MS", "50"))
    BULK_OPERATION_THRESHOLD_MS = float(os.getenv("BULK_OPERATION_THRESHOLD_MS", "200"))
    ENABLE_PERFORMANCE_DEBUG = os.getenv("ENABLE_PERFORMANCE_DEBUG", "false").lower() == "true"