import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- 1. Supabase 클라이언트 라이브러리 import ---
from supabase import create_client, Client

# --- 2. DB 관련 import 삭제 ---
# from sqlalchemy.orm import Session
# from ..db import database, models (삭제)

# --- 3. Supabase 클라이언트 초기화 ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client = None # 먼저 None으로 초기화

if not SUPABASE_URL or not SUPABASE_KEY:
    print("🚨 치명적 오류: .env 파일에 SUPABASE_URL 또는 SUPABASE_SERVICE_KEY가 없습니다!")
else:
    try:
        # --- 👇 URL 끝에 슬래시(/) 강제 추가 ---
        if not SUPABASE_URL.endswith('/'):
            SUPABASE_URL += '/'
            print("🔧 경고: .env 파일의 SUPABASE_URL 끝에 슬래시가 없어 코드에서 추가했습니다.")
        # ------------------------------------

        print(f" supabase 클라이언트 초기화 시도... (URL: {SUPABASE_URL})") # 사용될 URL 출력
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ auth.py: Supabase 클라이언트 초기화 성공!")
    except Exception as e:
        print(f"🚨 치명적 오류: Supabase 클라이언트 초기화 실패! {e}")
        
# 이 클라이언트가 SQLAlchemy의 'db' 역할을 대신합니다.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- 비밀번호 암호화 설정 (변경 없음) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- JWT 설정 (변경 없음) ---
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10))

def verify_password(plain_password, hashed_password):
    """(변경 없음)"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """(변경 없음)"""
    return pwd_context.hash(password)

def create_access_token(data: dict):
    """(변경 없음)"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- OAuth2 스킴 (변경 없음) ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    (로직 변경) JWT 토큰을 검증하고, Supabase API를 통해 사용자 정보를 조회합니다.
    """
    # --- 👇 확인용 print 추가 ---
    print("▶️ get_current_user 함수 시작됨")
    # ---------------------------
    # --- 👇 클라이언트 존재 여부 확인 추가 ---
    if not supabase:
        print("🚨 오류: get_current_user 내부 - Supabase 클라이언트가 없습니다!")
        raise HTTPException(status_code=500, detail="서버 설정 오류: 클라이언트 없음")
    # -----------------------------------

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 토큰 복호화 (변경 없음)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # --- 4. DB 조회 로직 변경 (SQLAlchemy -> Supabase API) ---
    # 'pro_new_page'는 Supabase에 있는 실제 테이블 이름입니다.
    # --- 👇 DB 조회 전 print 추가 ---
    print(f"🔍 Supabase에서 사용자 조회 시도: {email}")
    # ---------------------------
    response = supabase.table('pro_new_page').select('*').eq('email', email).execute()
    
    if not response.data:
        print(f"❌ 사용자 조회 실패: {email}")
        raise credentials_exception
    
    # user는 이제 DB 모델 객체가 아닌, Python 딕셔너리(dict)입니다.
    user_data = response.data[0] 
    # --- 👇 최종 반환 전 print 추가 ---
    print(f"✅ 사용자 조회 성공 및 반환: {email}")
    # ---------------------------
    return user_data