# backend-server/app/main.py
# uvicorn app.main:app --reload
import os
import uuid
import json
import base64 # ✅ [추가] Base64 디코딩용
from google.oauth2 import service_account # ✅ [추가] 구글 인증 객체 생성용
from fastapi import FastAPI, Depends, HTTPException, status
from dotenv import load_dotenv
load_dotenv() # 최우선 로드

# --- 👇 GCS 라이브러리 import ---
from google.cloud import storage
from datetime import timedelta
# --- 👇 2. Vertex AI 라이브러리 Import ---
import vertexai
from vertexai.generative_models import GenerativeModel
# ------------------------------------
# -----------------------------
import hmac
import hashlib
from typing import Optional, List
from pydantic import BaseModel
from .schemas import user as user_schemas
from .services import auth as auth_service

# ✅ (수정) 4-1, 4-2단계에서 생성한 모듈 import
from .schemas import generation as generation_schemas
from . import validator

from fastapi.middleware.cors import CORSMiddleware
# =====================================================================
# ✅ [수정] 구글 클라우드 인증 (로컬 파일 vs 프로덕션 Base64 자동 감지)
# =====================================================================
google_credentials = None # 인증 객체를 담을 변수

# 1. 환경 변수에서 Base64 키를 찾아봅니다. (서버 배포용)
google_base64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")

if google_base64:
    try:
        print("🔒 [보안] 클라우드 환경 감지: Base64 인증 정보를 로드합니다.")
        # Base64 문자열 -> JSON 문자열 -> 파이썬 딕셔너리 -> 인증 객체
        creds_json = base64.b64decode(google_base64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        google_credentials = service_account.Credentials.from_service_account_info(creds_dict)
    except Exception as e:
        print(f"🚨 Base64 인증 정보 로드 실패: {e}")
else:
    print("💻 [개발] 로컬 환경 감지: GOOGLE_APPLICATION_CREDENTIALS 파일 경로를 사용합니다.")
    # 로컬에서는 아무것도 안 해도 라이브러리가 알아서 .env의 파일 경로를 찾습니다.
# =====================================================================
# --- GCS 클라이언트 초기화 ---
try:
    # ✅ [수정] 위에서 만든 credentials가 있으면 그걸 쓰고, 없으면 알아서 파일 찾게 둠
    if google_credentials:
        storage_client = storage.Client(credentials=google_credentials)
    else:
        storage_client = storage.Client() # 로컬 파일 자동 로드
        
    print("✅ Google Cloud Storage 클라이언트 초기화 성공!")
except Exception as e:
    print(f"🚨 Google Cloud Storage 클라이언트 초기화 실패: {e}")
    storage_client = None
# ---------------------------

# --- 👇 5. Vertex AI 클라이언트 초기화 ---
YOUR_PROJECT_ID = "new-create-page"
YOUR_LOCATION = "us-central1"

try:
    # ✅ [수정] credentials 파라미터 추가
    vertexai.init(
        project=YOUR_PROJECT_ID, 
        location=YOUR_LOCATION, 
        credentials=google_credentials # 인증 객체 전달 (없으면 None, 자동 로드)
    )
    
    gemini_model = GenerativeModel("gemini-2.5-pro") 
    print(f"✅ Vertex AI (Gemini) 모델이 성공적으로 설정되었습니다. (리전: {YOUR_LOCATION})")
except Exception as e:
    print(f"🚨 Vertex AI 모델 설정 중 오류 발생: {e}")
    gemini_model = None

# ... (환경 변수 로드) ...
SUPABASE_URL = os.getenv("SUPABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10))
# ... (PLAN_CREDITS 정의) ...

PLAN_CREDITS = {
    "Starter": 50,
    "Standard": 150,
    "Pro": 500
}

app = FastAPI(
    title="상세페이지 자동 제작기 백엔드",
    description="사용자 인증, GPT/MCP 중계, 요금제 관리를 위한 API 서버",
    version="1.0.0",
)

# --- CORS 설정 (변경 없음) ---
origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 데이터 모델 정의 ---
class SignedUrlRequest(BaseModel):
    file_name: str

class SignedUrlResponse(BaseModel):
    signed_url: str
    public_url: str

# --- API 엔드포인트 ---

@app.post("/api/storage/request-upload-url", response_model=SignedUrlResponse)
def request_upload_url(
    request_data: SignedUrlRequest,
    current_user: dict = Depends(auth_service.get_current_user)
):
    if not storage_client:
        raise HTTPException(status_code=500, detail="Storage 클라이언트가 초기화되지 않았습니다.")

    bucket_name = "projectresolutionsoffice-no2-product-images"
    file_name = request_data.file_name

    try:
        _, ext = os.path.splitext(file_name)
        blob_name = f"images/{uuid.uuid4()}{ext}"
    except Exception as e:
        print(f"잘못된 파일 이름 형식입니다: {e}")
        raise HTTPException(status_code=400, detail=f"잘못된 파일 이름 형식입니다")

    try:
        print(f" 🚀 GCS에 서명된 URL 요청 시도: bucket='{bucket_name}', blob='{blob_name}'")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=60),
            method="PUT",
            content_type=f"image/{ext[1:].lower()}"
        )
        print(f" ✅ GCS 서명된 URL 생성 성공")

    except Exception as e:
        print(f" ❌ GCS 서명된 URL 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"스토리지 URL 생성에 실패했습니다")

    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    print(f" 🔗 공개 URL 생성됨: {public_url}")

    return {"signed_url": signed_url, "public_url": public_url}

# --- (이하 /register, /login, /me 엔드포인트는 변경 사항 없음) ---
@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(user_data: user_schemas.UserCreate):
    response = auth_service.supabase.table('pro_new_page').select('id').eq('email', user_data.email).execute()
    if response.data:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    customer_type = 0
    remaining_generations = 0
    plan_type = "None"
    if user_data.license_key:
        try:
            parts = user_data.license_key.split('-')
            if len(parts) != 4 or parts[0] != "PRO":
                raise ValueError("Invalid format")
            key_plan_name = parts[1]
            nonce = parts[2]
            received_signature = parts[3]
            base_key = f"PRO-{key_plan_name}-{nonce}"
            expected_signature_full = hmac.new(
                key=SECRET_KEY.encode('utf-8'),
                msg=base_key.encode('utf-8'),
                digestmod=hashlib.sha256
            ).hexdigest()
            expected_signature = expected_signature_full[:8]
            if not hmac.compare_digest(received_signature, expected_signature):
                raise ValueError("Invalid signature")
        except Exception as e:
            print(f"라이선스키 검증 실패: {e}")
            raise HTTPException(status_code=400, detail="라이선스키가 유효하지 않거나 형식이 올바르지 않습니다.")
        response = auth_service.supabase.table('pro_new_page').select('id').eq('license_key', user_data.license_key).execute()
        if response.data:
            raise HTTPException(status_code=400, detail="이미 사용된 라이선스키입니다.")
        if key_plan_name in PLAN_CREDITS:
            customer_type = 1
            plan_type = key_plan_name
            remaining_generations = PLAN_CREDITS[key_plan_name]
        else:
            raise HTTPException(status_code=400, detail="키는 유효하나, 존재하지 않는 요금제입니다.")
    hashed_password = auth_service.get_password_hash(user_data.password)
    new_user_data = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "license_key": user_data.license_key,
            "customer_type": customer_type,
            "plan_type": plan_type,
            "remaining_generations": remaining_generations
        }
    try:
        auth_service.supabase.table('pro_new_page').insert([new_user_data]).execute()
    except Exception as e:
        print(f"데이터베이스 저장에 실패했습니다: {e}")
        raise HTTPException(status_code=500, detail=f"데이터베이스 저장에 실패했습니다")
    return {"message": "회원가입이 성공적으로 완료되었습니다."}

# 1. response_model을 'Token'에서 'LoginResponse'로 변경
@app.post("/api/auth/login", response_model=user_schemas.LoginResponse)
def login_for_access_token(form_data: user_schemas.UserLogin):
    
    # (Supabase 조회 로직 - 그대로 유지)
    response = auth_service.supabase.table('pro_new_page').select('*').eq('email', form_data.email).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = response.data[0] # DB에서 가져온 사용자 정보 딕셔너리
    
    # (비밀번호 확인 로직 - 그대로 유지)
    if not auth_service.verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = auth_service.create_access_token(data={"sub": user['email']})
    
    # 🔥 [핵심 수정] 클라이언트가 원하는 정보를 모두 담아서 리턴!
    # Supabase의 'pro_new_page' 테이블에 'agreedseq' 컬럼이 있어야 합니다.
    # 만약 컬럼이 없거나 비어있으면 에러가 날 수 있으니 .get()으로 안전하게 가져옵니다.
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user['email'],             # 이메일을 username으로 전달
        "agreedseq": user.get('agreedseq', 0)  # DB 값 전달 (없으면 0)
    }

@app.get("/api/users/me", response_model=user_schemas.UserInfo)
def read_users_me(current_user: dict = Depends(auth_service.get_current_user)):
    return {
        "email": current_user['email'],
        "plan_type": current_user['plan_type'],
        "remaining_generations": current_user['remaining_generations']
    }
# --- (로컬 GenerationRequest 클래스 정의 삭제됨) ---

@app.post("/api/generate/page")
def generate_page(
    request_data: generation_schemas.GenerationRequest,
    current_user: dict = Depends(auth_service.get_current_user)
):
    if current_user['remaining_generations'] <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="남아있는 생성 횟수가 없습니다. 횟수를 충전해주세요."
        )

    new_credits = current_user['remaining_generations'] - 1
    
    if not gemini_model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vertex AI (Gemini) 모델이 초기화되지 않았습니다."
        )

    try:
        specs_str = "\n".join(f"- {spec}" for spec in request_data.product_info.specs)
        benefits_str = "\n".join(f"- {benefit}" for benefit in request_data.product_info.benefits)
        image_list_str = "\n".join(f"- {url}" for url in request_data.product_info.image_urls)
        
        user_reviews = request_data.product_info.reviews
        shipping_info = request_data.product_info.shipping_info
        selected_tone = request_data.generation_options.tone or '기본 (정보 전달 중심)'

        # --- (단순화된 AI 마스터 프롬프트 - 변경 없음) ---
        prompt = (
            f"당신은 'Figma'를 사용하는 시니어 아트 디렉터입니다. 당신의 임무는 '입력 데이터'를 바탕으로 '창의적인 디자인' JSON을 생성하는 것입니다.\n"
            f"**🚨 중요: 당신의 역할이 변경되었습니다! 🚨**\n"
            f"당신은 더 이상 '픽셀 계산'을 할 필요가 없습니다. (예: 텍스트 높이, 겹침 방지 y좌표, 캔버스 높이)\n"
            f"**Python 'Validator'가 당신의 디자인(JSON)을 받은 후, 모든 '계산 오류'(겹침, 높이, 빈 공간)를 100% 자동으로 수정할 것입니다.**\n"
            f"이제 계산은 Validator에게 맡기고, 당신은 **오직 '디자인'과 '가독성'에만 집중**하세요.\n\n"
            f"--- 🚨 치명적인 디자인 규칙 (Fatal Design Rules) - (이것에만 집중하세요!) 🚨 ---\n"
            f"1. **(가독성 1순위!)** 텍스트의 `color`는 배경색과 대비되어야 합니다.\n"
            f"   - **(밝은 배경/shape 위):** 텍스트 `color`는 **반드시 어두운 색** (예: `#111111`)이어야 합니다.\n"
            f"   - **(어두운 배경/shape/이미지 위):** 텍스트 `color`는 **반드시 밝은 색** (예: `#FFFFFF`)이어야 합니다.\n"
            f"   - **(이미지 위 텍스트):** 텍스트가 이미지 위에 올라갈 경우, **반드시 어두운 오버레이 `shape`** (예: `backgroundColor: 'rgba(0,0,0,0.5)'`, `zIndex: 5`)를 텍스트(zIndex 10) 뒤에 깔아 가독성을 보장하세요.\n"
            f"   - **(치명적 오류):** **밝은 배경에 흰색 텍스트**는 **절대 금지**입니다.\n"
            f"2. **(줄 간격 및 글자 수) - (디자인 규칙)**\n"
            f"   - **소제목(H1, H2)**: `lineHeight` = 1.0~1.1 (글자가 밀착되게)\n"
            f"   - **본문(Body)**: `lineHeight` = 1.25 (읽기 편하게)\n"
            f"   - **(간결성)** 모든 '본문(Body)' 텍스트는 **3줄 이내**, 문장당 **40자 이하**로 **'당신이 직접' 요약**하세요.\n"
            f"3. **(영역 구분!)** 지루하게 쌓지 마세요. **`shape`**를 사용해 **`#FFFFFF`와 `#F9F9F9`을 교차로 배치**하는 배경 섹션을 만드세요.\n"
            f"4. **(Figma 퀄리티!)** '{selected_tone}' 톤에 맞춰, **'좌우 2단 배치(이미지-텍스트)'** 및 **'이미지 위에 텍스트 겹치기'** 레이아웃을 창의적으로 사용하세요. (겹칠 때는 '규칙 1' 준수!)\n"
            f"5. **(모바일 가독성!)** 폰트 크기를 과감하게 사용하세요.\n"
            f"   - **본문 텍스트: `34px` ~ `38px`**\n"
            f"   - **헤드라인: `50px` ~ `90px`**\n"
            f"6. **(키 이름 고정!)** 이미지 URL 키는 **'src'**, 텍스트 내용 키는 **'content'**를 고정하세요.\n"
            f"7. **(데이터 기반 생성!)** (기존 규칙 10 수정)\n"
            f"   - 사용자가 제공한 리뷰(`user_reviews`)와 배송/AS 정보(`shipping_info`)가 **존재할 경우**, **반드시 상세페이지에 포함**하세요. (누락 금지)\n"
            f"   - **(가독성 보장)** 리뷰/배송 섹션이 이미지 위에 배치될 경우, '규칙 1'의 오버레이/대비 규칙을 준수하세요.\n"
            f"8. **(HTML 태그 금지!)** `content`에 HTML 태그(`<br>`, `<p>`)를 절대 포함하지 마세요. 줄바꿈은 오직 **`\\n`**으로만 표현하세요.\n"
            f"9. **(JSON 유효성!)** 100% 완벽한 JSON만 반환하세요.\n"
            f"--- 입력 데이터 (Input) ---\n"
            f"* 상품명: {request_data.product_info.product_name}\n"
            f"* 가격: {request_data.product_info.price or '가격 정보 없음'}\n"
            f"* 주요 사양 (Fact):\n{specs_str}\n"
            f"* 핵심 혜택 (Benefit):\n{benefits_str}\n"
            f"* 타겟 고객: {request_data.product_info.target_audience or '전체 소비자'}\n"
            f"* 원하는 톤앤매너: **{selected_tone}**\n"
            f"* 사용 가능 이미지 URL:\n{image_list_str}\n"
            f"* 사용자 제공 리뷰:\n{user_reviews or '제공되지 않음'}\n"
            f"* 사용자 제공 배송/AS 정보:\n{shipping_info or '제공되지 않음'}\n\n"
            f"--- 상세페이지 필수 구조 (Structure) --- (위 9가지 디자인 규칙을 준수하며 생성)\n"
            f"1. 도입부 (Attention)\n"
            f"2. 공감 및 해결책 제시 (Interest)\n"
            f"3. 핵심 혜택 (Desire)\n"
            f"4. 신뢰 확보 (Conviction): (규칙 7 준수)\n"
            f"5. 상세 스펙 (Details)\n"
            f"6. 행동 유도 (Action): (규칙 7 준수)\n\n"
            f"--- 이미지 규칙 (Image Rule) ---\n"
            f"* **이미지 누락 방지!**\n"
            f"  - 모든 입력 이미지 URL 중 최소 3개 이상을 반드시 사용하세요.\n"
            f"  - 이미지가 누락되면 `F9F9F9` 배경 위에 기본 placeholder를 추가하세요.\n"
            f"--- 전문 디자인 가이드라인 (Design) ---\n"
            f"* **(필수) 톤앤매너 번역 가이드:**\n"
            f"   - '{selected_tone}' 톤에 맞춰, **상품 이미지에서 메인 컬러 1개, 서브 컬러 1개를 추출**하여 `backgroundColor`, `color` 등에 일관되게 적용하세요.\n"
            f"   - (예: '전문적/심플'이면 `#FFFFFF` 배경, `#111111` 텍스트, `#007ACC` 강조색, 깔끔한 좌우 2단 그리드 사용)\n"
            f"   - (예: '따뜻함/감성적'이면 `#F9F5F0` 배경, `#4E4A47` 텍스트, `#D9A167` 강조색, 비대칭 또는 겹침 레이아웃 시도)\n"
            f"* 타이포그래피 (폰트 계층): 'Noto Sans KR' 통일. (규칙 2, 5 준수)\n"
            f"   - H1 (메인 헤드라인): 72-90px, 900(Black), lineHeight 1.0~1.1\n"
            f"   - H2 (섹션 제목): 50-60px, 700(Bold), lineHeight 0.0~0.1\n"
            f"   - Body (본문): 34-38px, 400/500(Regular/Medium), lineHeight 1.25\n"
            f"* zIndex: 이미지=1, 도형 배경=5, 텍스트=10\n\n"
            f"--- 출력 형식 (Output Format) ---\n"
            f"오직 JSON 객체 하나만 반환하세요. (앞뒤 설명, ` ```json ` 마크다운 절대 금지)\n"
            f"**중요:** `y`, `height` 값은 **'디자인 초안'**으로 제공하세요. Validator가 이 값을 기준으로 수정할 것입니다.\n"
            f"{{\n"
            f"  \"canvas\": {{\"width\": 1080, \"height\": 8000, \"backgroundColor\": \"#F9F9F9\"}},\n"
            f"  \"layers\": [\n"
            f"    // ... (모든 '디자인' 규칙을 준수하여 생성) ...\n"
            f"  ]\n"
            f"}}"
        )
        
        # --- (프롬프트 끝) ---

        print("단순화된 프롬프트로 Gemini에 JSON 레이아웃 생성을 요청합니다...")
        response = gemini_model.generate_content(prompt)

        raw_ai_response = response.text
        print("--- 🤖 AI 원본 응답 ---")
        print(raw_ai_response)
        print("----------------------")
        
        json_string = raw_ai_response.strip().replace("```json", "").replace("```", "").strip()
        print("--- 🧹 정리된 JSON 문자열 ---")
        print(json_string)
        print("---------------------------")
        ai_generated_layout = json.loads(json_string)
        print("✅ AI JSON 파싱 성공!")

        # --- Validator 자동 보정 단계 ---
        print("🐍 Validator 자동 보정 시작 (텍스트 높이 재계산, 겹침 제거, 캔버스 높이 재조정)...")
        fixed_layout = validator.validate_and_autofix_layout(ai_generated_layout)
        
        # --- ✅ (신규) 3단계 요청: 'Validator 최종본' 로깅 추가 ---
        # (ensure_ascii=False는 로그에서 한글이 깨지지 않게 합니다)
        print("--- 🐍 Validator 최종 JSON (보정본) ---")
        try:
            print(json.dumps(fixed_layout, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Validator 최종본 로깅 실패: {e}")
        print("---------------------------------")
        # --- (로깅 추가 끝) ---
        
        print("✅ Validator 자동 보정 완료!")
        
        # 2. 횟수 차감 (AI 호출 및 Validator 보정 성공 후)
        try:
            auth_service.supabase.table('pro_new_page').update({'remaining_generations': new_credits}).eq('id', current_user['id']).execute()
            print(f"✅ 횟수 차감 완료. 남은 횟수: {new_credits}")
        except Exception as e:
            print(f"🚨 경고: AI 생성은 성공했으나 DB 횟수 차감에 실패했습니다: {e}")
            pass

    except Exception as e:
        print(f"🚨 오류: AI 응답 처리 또는 Validator 실행 중 예외 발생: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI 서비스 호출 또는 응답 처리 중 오류가 발생했습니다"
        )
    
    # 5. 최종 결과 반환
    print("✅ 자동 보정된 layout_data 포함하여 클라이언트에 응답 전송")
    return {
        "message": "JSON 레이아웃 생성이 성공적으로 완료되었습니다.",
        "layout_data": fixed_layout,
        "remaining_generations": new_credits
    }
# ==========================================
# 👇 [신규] 앱 자동 업데이트를 위한 API 엔드포인트
# ==========================================
class AppVersion(BaseModel):
    version: str
    download_url: str
    force_update: bool

@app.get("/api/app-version", response_model=AppVersion)
def check_app_version():
    """
    런처(Launcher)가 호출하는 API: 최신 버전 정보를 반환합니다.
    새 버전을 배포할 때마다 아래 'version'과 'download_url'을 수정하면 됩니다.
    """
    return {
        "version": "0.0.2",  # 🔥 배포할 최신 버전 (version.txt보다 높아야 업데이트됨)
        
        # 👇 [중요] 아까 GitHub Releases에서 복사한 '링크 주소'를 여기에 넣으세요!
        "download_url": "https://github.com/ProjectResolutionsOffice/new_create_page_main/releases/download/v0.0.2/update_v0.0.2.zip",
        
        "force_update": True # True면 강제 업데이트 권장 알림
    }