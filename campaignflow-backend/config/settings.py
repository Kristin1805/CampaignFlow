
"""
Django settings for config project.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Security

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_ratelimit",

    "campaignflow.authentication",
    "campaignflow.organization",
    "campaignflow.clients",
    "campaignflow.campaigns",
    "campaignflow.tasks",
    "campaignflow.documents",
    "campaignflow.approvals",
    "campaignflow.calendar_app",
    "campaignflow.optimizer",
    "campaignflow.analytics",
    "campaignflow.dashboard",
    "campaignflow.notifications",
    "campaignflow.content.apps.ContentConfig",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"


# Database configuration

required_db_variables = (
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
)

missing_db_variables = [
    variable
    for variable in required_db_variables
    if not os.getenv(variable)
]

if missing_db_variables:
    raise ImproperlyConfigured(
        "Missing PostgreSQL environment variables: "
        + ", ".join(missing_db_variables)
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ["DB_PORT"],
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Authentication

AUTH_USER_MODEL = "authentication.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "campaignflow.core.authentication.CampaignFlowSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files
STATIC_URL = 'static/'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

DEFAULT_FROM_EMAIL = "CampaignFlow <noreply@campaignflow.local>"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# Celery / RabbitMQ

CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]

CELERY_RESULT_BACKEND = "rpc://"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

CELERY_TASK_TRACK_STARTED = True


# Default primary key field type

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Redis cache

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    }
}


# Frontend

FRONTEND_URL = "http://localhost:5173"


# Private media

PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"


# CampaignFlow Optimizer / C++ Engine

CFENGINE_PATH = os.getenv(
    "CFENGINE_PATH",
    "cfengine",
)

try:
    CFENGINE_TIMEOUT = int(
        os.getenv("CFENGINE_TIMEOUT", "10")
    )
except ValueError as exc:
    raise ImproperlyConfigured(
        "CFENGINE_TIMEOUT must be an integer."
    ) from exc

if CFENGINE_TIMEOUT <= 0:
    raise ImproperlyConfigured(
        "CFENGINE_TIMEOUT must be greater than zero."
    )


CFENGINE_INPUT_SCHEMA = (
    BASE_DIR
    / "contracts"
    / "optimize.input.schema.json"
)

CFENGINE_OUTPUT_SCHEMA = (
    BASE_DIR
    / "contracts"
    / "optimize.output.schema.json"
)
