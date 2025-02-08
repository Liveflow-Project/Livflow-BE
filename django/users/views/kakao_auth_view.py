import os
import requests
import logging
from django.utils.text import slugify
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from users.utils import store_refresh_token  

# 로깅 설정
logger = logging.getLogger(__name__)

User = get_user_model()

@method_decorator(csrf_exempt, name='dispatch')
class KakaoExchangeCodeForToken(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        logger.info("🔍 Kakao OAuth 요청 시작")

        code = request.data.get("code")
        logger.info(f"📌 받은 Authorization Code: {code}")

        if not code:
            logger.error("❌ Authorization Code가 없습니다.")
            return JsonResponse({"error": "Authorization code is missing"}, status=400)

        token_endpoint = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": os.getenv("KAKAO_CLIENT_ID"),
            "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),  
            "redirect_uri": os.getenv("KAKAO_REDIRECT_URI"),
            "code": code,
        }

        try:
            # ✅ 카카오에서 액세스 토큰 요청
            response = requests.post(token_endpoint, data=data)
            logger.info(f"📌 Kakao OAuth 응답 상태 코드: {response.status_code}")

            response.raise_for_status()
            token_data = response.json()
            logger.info(f"📌 Kakao OAuth Token Response: {token_data}")

            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("❌ Kakao에서 Access Token을 가져오지 못했습니다.")
                return JsonResponse({"error": "Failed to obtain access token"}, status=400)

            # ✅ 카카오에서 사용자 정보 가져오기
            userinfo_endpoint = "https://kapi.kakao.com/v2/user/me"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = requests.get(userinfo_endpoint, headers=headers)
            user_info_response.raise_for_status()
            user_info = user_info_response.json()
            logger.info(f"📌 Kakao User Info Response: {user_info}")

            kakao_account = user_info.get("kakao_account", {})
            email = kakao_account.get("email")
            full_name = kakao_account.get("profile", {}).get("nickname", "").strip()

            # ✅ 이메일 제공 여부 확인
            if kakao_account.get("email_needs_agreement"):
                logger.warning("⚠️ 사용자가 이메일 제공에 동의하지 않았습니다.")
                return JsonResponse({"error": "User did not agree to share email"}, status=400)

            if not email:
                logger.error("❌ Kakao User Info에 이메일 정보가 없습니다.")
                return JsonResponse({"error": "Email not found in user info"}, status=400)

            # ✅ `username` 자동 생성 (이메일이 없는 경우 Kakao ID 사용)
            base_username = slugify(email.split("@")[0]) if email else f"kakao_{user_info['id']}"
            username = base_username

            # ✅ 이미 존재하는 `username`이 있으면 숫자 추가해서 중복 방지
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            # ✅ `get_or_create()` 사용 시, `username`을 명시적으로 지정
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"username": username, "first_name": full_name}
            )
            logger.info(f"✅ User 정보: {user} (Created: {created})")

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            logger.info("✅ JWT 토큰 생성 완료")

            expires_in = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())  
            store_refresh_token(user.id, refresh_token, expires_in)
            logger.info(f"✅ Redis에 Refresh Token 저장 완료 (Expires in: {expires_in}s)")

            response_data = {"access": access_token}
            response = JsonResponse(response_data)

            response.set_cookie(
                "access_token",
                access_token,
                domain=".livflow.co.kr",
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
                samesite="Strict",
            )
            logger.info("✅ 액세스 토큰을 쿠키에 저장 완료")

            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Kakao OAuth 요청 실패: {str(e)}")
            return JsonResponse({"error": f"Kakao OAuth Request Failed: {str(e)}"}, status=500)

        except Exception as e:
            logger.error(f"❌ 내부 서버 오류 발생: {str(e)}")
            return JsonResponse({"error": f"Internal Server Error: {str(e)}"}, status=500)
