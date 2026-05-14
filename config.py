import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY               = os.getenv("SECRET_KEY", "dev_key_change_en_prod")
    SQLALCHEMY_DATABASE_URI  = os.getenv("DATABASE_URL", "sqlite:///databroker229.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER            = "uploads"
    MAX_CONTENT_LENGTH       = 5 * 1024 * 1024

    # Marge
    MARGE                    = float(os.getenv("MARGE", "0.40"))

    # Email
    EMAIL_EXPEDITEUR         = os.getenv("EMAIL_EXPEDITEUR", "")
    EMAIL_MOT_DE_PASSE       = os.getenv("EMAIL_MOT_DE_PASSE", "")
    EMAIL_NOM                = "DataBroker 229"

    # Contacts
    WHATSAPP                 = "+22961976712"
    TELEPHONE                = "+2290155256871"

    # Africa's Talking
    AT_USERNAME              = os.getenv("AT_USERNAME", "sandbox")
    AT_API_KEY               = os.getenv("AT_API_KEY", "")

    # Kkiapay
    KKIAPAY_PUBLIC_KEY       = os.getenv("KKIAPAY_PUBLIC_KEY", "")
    KKIAPAY_PRIVATE_KEY      = os.getenv("KKIAPAY_PRIVATE_KEY", "")
    KKIAPAY_SANDBOX          = os.getenv("KKIAPAY_SANDBOX", "true").lower() == "true"

    # Admin
    ADMIN_PASSWORD           = os.getenv("ADMIN_PASSWORD", "databroker229")

    # Validation auto
    GPS_TOLERANCE_KM         = 5.0
    MIN_COLLECTES_VALID      = 3
