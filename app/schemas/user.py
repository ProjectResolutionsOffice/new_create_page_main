from pydantic import BaseModel, EmailStr
from typing import Optional # Python의 기본 typing 라이브러리에서 Optional을 가져옵니다.

# 회원가입 시 받을 데이터 형식
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    license_key: Optional[str] = None # license_key는 문자열이거나 없을(None) 수 있습니다.

# 로그인 시 받을 데이터 형식
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# 토큰을 응답할 때의 데이터 형식
class Token(BaseModel):
    access_token: str
    token_type: str

# 사용자 정보를 응답할 때의 데이터 형식 (비밀번호 제외)
class UserInfo(BaseModel):
    email: EmailStr
    plan_type: str             # ✅ "plan_type"으로 수정
    remaining_generations: int # ✅ "remaining_generations"로 수정