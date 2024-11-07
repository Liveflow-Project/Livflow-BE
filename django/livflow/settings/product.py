from .base import *  # base.py 설정을 가져옵니다.

# Debug 설정
DEBUG = False

# 허용된 호스트 (홈서버의 IP 주소나 도메인 추가)
ALLOWED_HOSTS = ['your-domain.com', 'localhost', '127.0.0.1']

# 데이터베이스 설정
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# SSL/HTTPS 설정
# Nginx를 통해 HTTPS로 통신하는 경우, Django와의 통신은 HTTP이므로 SECURE 설정을 조정해야 할 수 있습니다.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Static files (CSS, JavaScript, Images) 설정
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles'  # collectstatic 명령어로 생성된 파일 저장 위치
MEDIA_URL = '/media/'
MEDIA_ROOT = '/app/media'

# CORS 설정 (필요시)
CORS_ALLOWED_ORIGINS = [
    "https://www.livflow.co.kr",
    "http://localhost:5173"
]

# 기타 보안 설정
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_HSTS_SECONDS = 31536000  # 1년
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

ROOT_URLCONF = "livflow.urls"