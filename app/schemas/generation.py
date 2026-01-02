# backend-server/app/schemas/generation.py
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

# ---------------------------------------------------------------------------
# (이 파일은 app.schemas.user.py 와 별도로 상세페이지 생성 요청/응답만 담당합니다)
# (input_form.py의 get_data() 구조와 100% 일치하도록 작성됨)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1. 클라이언트 요청 스키마 (PySide6 -> FastAPI)
# ---------------------------------------------------------------------------

class ProductInfo(BaseModel):
    """
    PySide6(input_form.py)에서 수집된 실제 상품 정보.
    클라이언트(worker.py)가 get_data() 딕셔너리를 기반으로 이 모델을 구성해야 합니다.
    """
    product_name: str = Field(..., description="상품명 (from product_name_input)")
    price: str = Field(..., description="가격 (from price_input)")
    specs: List[str] = Field(default=[], description="주요 사양 (from specs_input)")
    target_audience: str = Field(..., description="타겟 고객 (from target_audience_input)")
    benefits: List[str] = Field(default=[], description="핵심 혜택 (from key_benefits_input)")
    image_urls: List[str] = Field(default=[], description="업로드된 모든 이미지 URL (from uploaded_image_urls)")
    reviews: str = Field(..., description="강조 리뷰 (from reviews_input)")
    shipping_info: str = Field(..., description="배송/AS 정보 (from shipping_input)")

class GenerationOptions(BaseModel):
    """
    AI 생성 방식을 제어하는 옵션.
    """
    tone: Optional[str] = Field(default=None, description="톤앤매너 (from tone_input)")

class GenerationRequest(BaseModel):
    """
    클라이언트(PySide6)에서 서버(/generate/page)로 보내는 메인 요청 모델
    """
    product_info: ProductInfo
    generation_options: GenerationOptions

# ---------------------------------------------------------------------------
# 2. 서버 응답 스키마 (FastAPI -> PySide6)
# (AI가 생성하고 Validator가 수정할 최종 JSON 구조)
# ---------------------------------------------------------------------------

class Canvas(BaseModel):
    """
    상세페이지 전체 캔버스 설정
    """
    width: int = Field(default=1200, description="상세페이지 고정 너비 (px)")
    height: int = Field(..., description="콘텐츠 길이에 따른 캔버스 높이 (AI가 제안하고 Validator가 최종 수정)")
    background_color: str = Field(default="#FFFFFF", description="캔버스 배경색")

class LayoutResponse(BaseModel):
    """
    AI가 생성하고 서버가 검증/수정한 최종 JSON 레이아웃
    preview_widget.py가 이 데이터를 받아 렌더링합니다.
    """
    canvas: Canvas
    layers: List[Dict[str, Any]] = Field(..., description="모든 디자인 요소(텍스트, 이미지, 도형)의 목록")