"""
Django settings for config project.
"""

import os
from pathlib import Path
from decouple import config
import dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

dotenv.load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-=jn_0%pd7iq^ictvns%o!7m(=l*!b@!b#(%4wtm+$k-1*wn0p8',
)

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
ALLOWED_HOSTS = ["https://lingua-learn.uz/", "lingua-learn.uz"]

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'core',
    'accounts',
    'courses',
    'writing',
    'speaking',
    'panel',
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
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'


# Database

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': os.environ.get('DB_PATH', BASE_DIR / 'db.sqlite3'),
#     }
# }


DATABASES = {
     'default': {
         'ENGINE': 'django.db.backends.mysql',
         'NAME': config('DATABASE_NAME'),
         'USER': config('DATABASE_USER'),
         'PASSWORD': config('DATABASE_PASSWORD'),
         'HOST': config('DATABASE_HOST', default='localhost'),
         'PORT': config('DATABASE_PORT', default='5432', cast=int),
     }
 }

# Custom user model

AUTH_USER_MODEL = 'accounts.User'


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


# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (uploaded course images, certificates, etc.)
MEDIA_URL = 'media/'
# MEDIA_ROOT = os.environ.get('MEDIA_ROOT', BASE_DIR / 'media')
MEDIA_ROOT = '/home/linguale/public_html/backmanager/media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django refuses a form with more than 1000 fields (400 Bad Request). The key vocabulary editor of the panel sends six
# fields per word (up to 300 words in a Part), so the limit is raised to fit it; ordinary forms send a few dozen.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 3000


# Auth redirects

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'courses:course_list'
LOGOUT_REDIRECT_URL = 'core:home'


# Shown to users whose accounts are waiting for admin activation (see .env)

ADMIN_TELEGRAM_URL = os.environ.get('ADMIN_TELEGRAM_URL', '')


# AI feedback on spoken answers (Speaking practice). Claude reads the text of what the student said; without a key
# the practice still works and the results page just says the AI feedback is not set up.

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '').strip()
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com').strip().rstrip('/')
SPEAKING_AI_MODEL = os.environ.get('SPEAKING_AI_MODEL', 'claude-sonnet-5-5').strip()
SPEAKING_FEEDBACK_LANGUAGE = os.environ.get('SPEAKING_FEEDBACK_LANGUAGE', 'English').strip()

# The free alternative, Groq (https://console.groq.com). With its key the recordings are turned into text on the server
# (Whisper), so the answers are checked in any browser, and Groq also writes the feedback when there is no Claude key.
# GROQ_MODEL must be one that answers in a given JSON schema (strict structured outputs), like the gpt-oss models.

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
GROQ_BASE_URL = os.environ.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').strip().rstrip('/')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'openai/gpt-oss-120b').strip()
GROQ_TRANSCRIPTION_MODEL = os.environ.get('GROQ_TRANSCRIPTION_MODEL', 'whisper-large-v3').strip()


# https. The "https" service of docker-compose.yml (nginx) answers on this port and passes the requests on to Django,
# saying in X-Forwarded-Proto that the visitor came over https. Browsers give the microphone only to https pages (and
# to localhost), so the Speaking practice sends visitors of the plain-http address to https://<same address>:HTTPS_PORT.
# Empty = there is no https address (running without Docker).

HTTPS_PORT = os.environ.get('HTTPS_PORT', '').strip()

# Only with that proxy in front: without it any visitor could claim "https" with this header.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if HTTPS_PORT else None
