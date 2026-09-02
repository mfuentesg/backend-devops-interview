import warnings
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    # Insecure dev-only default. Set a real SECRET_KEY in the environment for
    # any deployment; the previous checked-in key has been rotated out.
    SECRET_KEY=(str, "django-insecure-unsecure"),
    DEBUG=(bool, True),
    # Comma-separated. .env ships "*" for local dev so the Prometheus container
    # can scrape the host-run app via host.docker.internal; empty falls back to
    # .localhost / 127.0.0.1 / [::1] under DEBUG. Set explicit hosts for deploys.
    ALLOWED_HOSTS=(list, []),
    LANGUAGE_CODE=(str, "en-us"),
    TIME_ZONE=(str, "America/Santiago"),
    POSTGRES_DB=(str, "backend_devops_interview"),
    POSTGRES_USER=(str, "postgres"),
    POSTGRES_PASSWORD=(str, "postgres"),
    POSTGRES_HOST=(str, "localhost"),
    POSTGRES_PORT=(str, "5432"),
    LOG_DIR=(str, str(BASE_DIR / "logs")),
    LOG_JSON_FILE=(bool, False),
    LOG_LEVEL=(str, ""),  # blank → derived from DEBUG below
)
# Read a local .env file if present. Real environment variables always win,
# so this is a no-op in CI and production.
environ.Env.read_env(BASE_DIR / ".env")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "blog",
    "django_prometheus",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "blog.api.middleware.ApiEnvelopeErrorMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

LOG_LEVEL = env("LOG_LEVEL") or "INFO"
LOG_DIR = env("LOG_DIR")
LOG_JSON_FILE = env("LOG_JSON_FILE")

if not DEBUG and LOG_LEVEL == "DEBUG":
    warnings.warn(
        "LOG_LEVEL=DEBUG with DEBUG=False: debug-level logging in a non-debug "
        "deployment is a performance and PII-leak risk.",
        stacklevel=2,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
        "json": {"()": "core.json_log.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "loggers": {
        # Django's internal DEBUG logging is a firehose (every SQL query via
        # django.db.backends; every watched file via django.utils.autoreload).
        # Pin those two above LOG_LEVEL so an explicit LOG_LEVEL=DEBUG still
        # yields a readable console — lower them by hand when debugging SQL.
        name: {
            "handlers": ["console"],
            "level": "INFO"
            if name in ("django.db.backends", "django.utils.autoreload")
            else LOG_LEVEL,
            "propagate": False,
        }
        for name in (
            "django",
            "django.request",
            "django.server",
            "django.db.backends",
            "django.utils.autoreload",
            "blog",
        )
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

if LOG_JSON_FILE:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(Path(LOG_DIR) / "app.log"),
        "formatter": "json",
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 3,
    }
    for logger in LOGGING["loggers"].values():
        logger["handlers"].append("file")
    LOGGING["root"]["handlers"].append("file")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
LANGUAGE_CODE = env("LANGUAGE_CODE")
TIME_ZONE = env("TIME_ZONE")

USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
