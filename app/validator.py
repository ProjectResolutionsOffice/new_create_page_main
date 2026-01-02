import sys
from typing import Dict, Any, List, Tuple
import requests
from io import BytesIO
from PIL import Image

# ---------------------------------------------------------------------------
# (중요) Headless PySide6 Application Initialization
# ---------------------------------------------------------------------------
try:
    from PySide6.QtGui import QGuiApplication, QFont, QTextDocument, QTextBlockFormat, QTextCursor
    from PySide6.QtCore import QSize
except ImportError:
    print("CRITICAL ERROR: PySide6 is not installed in the backend environment.")
    print("Please run 'pip install PySide6' in your backend-server virtualenv.")
    sys.exit(1)

app_instance = None
def get_qt_app_instance():
    global app_instance
    app_instance = QGuiApplication.instance()
    if not app_instance:
        print("Initializing new QGuiApplication for headless text calculation...")
        app_instance = QGuiApplication(sys.argv if hasattr(sys, 'argv') else [])
    return app_instance

get_qt_app_instance()

# ---------------------------------------------------------------------------
# Validation and Autofix Logic
# ---------------------------------------------------------------------------

# 섹션 간, 요소 간 기본 여백
DEFAULT_PADDING = 30 
# 텍스트끼리의 좁은 여백
SMALL_PADDING = 15
CANVAS_WIDTH = 1080

def _get_image_original_size(image_url: str) -> Tuple[int, int]:
    """ 이미지 URL에서 원본 너비와 높이를 가져옵니다. """
    try:
        if not image_url or not image_url.startswith(('http://', 'https://')):
            return 100, 100 
        response = requests.get(image_url, stream=True, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        return img.width, img.height
    except Exception as e:
        return 100, 100 

def _calculate_text_height(layer: Dict[str, Any]) -> int:
    """ 텍스트 레이어의 실제 렌더링 높이를 계산합니다. """
    if not app_instance: return layer.get('height', 0)

    try:
        content = layer.get('content', '')
        layer_x = layer.get('x', 0)
        layer_width = layer.get('width', 0)
        if layer_width <= 0:
            layer_width = max(CANVAS_WIDTH - layer_x - 50, 400)
            
        font_family = layer.get('fontFamily', 'Noto Sans KR')
        font_size = layer.get('fontSize', 16)
        font_weight_value = layer.get('fontWeight', 400)
        line_height_ratio = layer.get('lineHeight', 1.25) 
        
        font = QFont()
        font.setFamily(font_family)
        font.setPixelSize(int(font_size))
        
        weight_val = 400
        try: weight_val = int(font_weight_value)
        except:
            if str(font_weight_value).lower() == 'bold': weight_val = 700
        font.setWeight(QFont.Weight(weight_val)) 

        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setPlainText(content) 
        doc.setTextWidth(layer_width)
        
        pixel_line_height = int(font_size * line_height_ratio)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(pixel_line_height, 3) 
        
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setBlockFormat(block_format)

        calculated_height = doc.documentLayout().documentSize().height()
        # 텍스트 잘림 방지 안전 여백
        return int(calculated_height) + 15

    except Exception as e:
        return layer.get('height', 0)


def _resolve_collisions_preserving_order(layers: List[Dict[str, Any]]) -> int:
    """
    [핵심 로직] 그룹 내부에서 '순서 역전' 없이 '겹침'을 해결합니다.
    반환값: 이 그룹의 최종 콘텐츠 높이 (max_y)
    """
    if not layers: return 0
    
    # ✅ [수정] 정렬 기준을 '현재 y'가 아니라 '원본 y(_original_y)'로 변경
    # 이렇게 하면 shift로 인해 순서가 뒤바뀌었더라도, 원래 순서대로 배치 로직이 실행됩니다.
    layers.sort(key=lambda l: (l.get('_original_y', 0), l.get('zIndex', 0), l.get('_original_idx', 0)))
    
    max_y_in_group = 0
    
    for i in range(len(layers)):
        curr = layers[i]
        
        # 현재 요소가 위치해야 할 최소 Y값 (초기값은 자신의 현재 위치)
        min_y_pos = curr.get('y', 0)
        
        # 2. 내 앞에 있는 모든 요소들과 충돌 검사
        for j in range(i):
            prev = layers[j]
            
            # 수평(X축) 겹침 확인 (2단 컬럼 보호)
            prev_x1 = prev.get('x', 0)
            prev_x2 = prev_x1 + prev.get('width', CANVAS_WIDTH)
            curr_x1 = curr.get('x', 0)
            curr_x2 = curr_x1 + curr.get('width', CANVAS_WIDTH)
            
            is_x_overlapping = max(prev_x1, curr_x1) < min(prev_x2, curr_x2)
            
            # 수직(Y축) 겹침 확인을 위한 이전 요소의 바닥 좌표
            prev_bottom = prev.get('y', 0) + prev.get('height', 0)
            
            # [충돌 조건]
            # A. 수평으로 겹치고
            # B. zIndex가 같거나 (텍스트 vs 텍스트)
            # C. 이전 요소가 이미지인 경우 (이미지는 텍스트를 밀어내야 함)
            should_push = False
            if is_x_overlapping:
                if prev.get('zIndex') == curr.get('zIndex'):
                    should_push = True
                elif prev.get('type') == 'image' and curr.get('type') == 'text':
                    should_push = True
            
            if should_push:
                # 겹침 발생 시 밀어낼 위치 계산
                padding = DEFAULT_PADDING
                # 텍스트끼리는 조금 더 가깝게
                if curr.get('type') == 'text' and prev.get('type') == 'text':
                    fs_curr = curr.get('fontSize', 30)
                    fs_prev = prev.get('fontSize', 30)
                    if fs_curr <= 45 and fs_prev <= 45:
                        padding = SMALL_PADDING
                
                candidate_y = prev_bottom + padding
                
                # 더 아래쪽으로 밀어야 한다면 갱신
                if candidate_y > min_y_pos:
                    min_y_pos = candidate_y

        # 3. 최종 위치 확정 (원래 위치보다 위로 갈 순 있어도, 겹치면 아래로 밀림)
        curr['y'] = int(min_y_pos)
        
        # 그룹 전체 높이 갱신
        curr_bottom = curr['y'] + curr['height']
        if curr_bottom > max_y_in_group:
            max_y_in_group = curr_bottom
            
    return max_y_in_group


def validate_and_autofix_layout(layout_data: Dict[str, Any]) -> Dict[str, Any]:
    if 'layers' not in layout_data or 'canvas' not in layout_data:
        print("Validator Error: Invalid layout data structure.")
        return layout_data

    layers = layout_data.get('layers', [])
    if not layers: return layout_data

    print("\n--- Validator: Starting layout autofix (Final Safety Logic) ---")

    # --- 1단계: 전처리 (높이 계산, 이미지 리사이징) ---
    print("Step 1: Pre-processing layers...")
    for idx, layer in enumerate(layers):
        layer['_original_idx'] = idx 
        layer['_height_diff'] = 0

        # ------------------------------------------------------------------
        # [솔루션] X축 및 너비 강제 보정 (Overflow 방지)
        # ------------------------------------------------------------------
        # 1. 안전 여백 설정 (양옆 40px)
        SAFE_MARGIN = 40
        MAX_X_BOUNDARY = CANVAS_WIDTH - SAFE_MARGIN # 1040px
        
        # 필수 키 초기화
        if 'x' not in layer: layer['x'] = SAFE_MARGIN
        if 'width' not in layer or layer['width'] <= 0:
            layer['width'] = CANVAS_WIDTH - (SAFE_MARGIN * 2)

        # 2. 오른쪽 삐져나감(Overflow) 감지 및 보정
        current_x = layer.get('x', SAFE_MARGIN)
        current_width = layer.get('width', 100)
        current_right_edge = current_x + current_width

        # 요소가 오른쪽 벽(1040px)을 뚫고 나갔다면?
        if current_right_edge > MAX_X_BOUNDARY:
            overflow_amount = current_right_edge - MAX_X_BOUNDARY
            
            # 전략 A: 위치를 왼쪽으로 당겨서 해결 가능한가? (x를 줄임)
            # 단, x가 너무 작아지면(왼쪽 벽 침범) 안 됨
            if current_x - overflow_amount >= SAFE_MARGIN:
                layer['x'] = current_x - overflow_amount
                # print(f"Fixed: Shifted layer left by {overflow_amount}px")
            
            # 전략 B: 당겨도 안 되면 너비를 줄임 (Resize)
            else:
                layer['x'] = SAFE_MARGIN # 왼쪽 벽에 붙임
                layer['width'] = MAX_X_BOUNDARY - SAFE_MARGIN # 꽉 차게 줄임
                # print(f"Fixed: Resized layer width to {layer['width']}px")

        # 3. (추가) 텍스트인데 너비가 너무 좁으면 강제로 늘림 (최소 300px)
        if layer.get('type') == 'text' and layer['width'] < 300:
             # 공간이 허락하는 한 늘림
             available_width = CANVAS_WIDTH - layer['x'] - SAFE_MARGIN
             layer['width'] = min(400, available_width)
        # ------------------------------------------------------------------

        # 원본 좌표 저장
        old_height = layer.get('height', 0)
        layer['_original_y'] = layer['y']
        layer['_original_height'] = old_height
        layer['_original_bottom'] = layer['y'] + old_height

        # 이미지 리사이징
        if layer.get('type') == 'image':
            image_src = layer.get('src')
            target_width = layer.get('width', CANVAS_WIDTH)
            if image_src and target_width > 0:
                orig_w, orig_h = _get_image_original_size(image_src)
                if orig_w > 0:
                    new_height = int(target_width * (orig_h / orig_w))
                    layer['height'] = new_height
                    if old_height > new_height:
                        layer['_height_diff'] = old_height - new_height
                elif old_height <= 0: layer['height'] = 200
        
        # 텍스트 높이 계산
        elif layer.get('type') == 'text':
            # 정렬 보정 (스펙 등)
            content = layer.get('content', '')
            if any(c in content for c in [':', '-', '•']) or content.count('\n') > 1:
                if layer.get('fontSize', 16) < 60: layer['textAlign'] = 'left'
            layer['height'] = _calculate_text_height(layer)

        if layer.get('height', 0) == 0: layer['height'] = 100

    # --- 2단계: 그룹핑 (배경 Shape 기준) ---
    print("Step 2: Grouping...")
    # 배경 Shape 찾기
    backgrounds = sorted([l for l in layers if l.get('type') == 'shape' and l.get('zIndex', 10) <= 5], 
                         key=lambda l: l.get('y', 0))
    
    other_layers = [l for l in layers if l not in backgrounds]
    
    # 그룹 구조 생성
    sections = []
    for bg in backgrounds:
        sections.append({
            'background': bg,
            'content': []
        })
        
    # 콘텐츠 레이어들을 가장 적절한 배경 그룹에 할당
    # (단순 포함 관계가 아니라, '시각적 근접성'으로 판단)
    orphans = []
    
    for l in other_layers:
        l_center_y = l.get('y', 0) + (l.get('height', 0) / 2)
        assigned = False
        
        # 가장 가까운 배경 찾기
        best_bg_idx = -1
        min_dist = float('inf')
        
        for idx, bg in enumerate(backgrounds):
            bg_y_start = bg.get('y', 0)
            bg_y_end = bg_y_start + bg.get('_original_height', 1000) # 줄어들기 전 높이 기준
            
            # 1. 완벽 포함 확인
            if l.get('y', 0) >= bg_y_start and l.get('y', 0) < bg_y_end:
                sections[idx]['content'].append(l)
                assigned = True
                break
            
            # 2. 거리 계산 (포함되지 않았을 경우를 대비)
            dist = 0
            if l_center_y < bg_y_start: dist = bg_y_start - l_center_y
            elif l_center_y > bg_y_end: dist = l_center_y - bg_y_end
            
            if dist < min_dist:
                min_dist = dist
                best_bg_idx = idx
        
        # 포함되지 않았더라도, 거리가 매우 가깝다면(예: 50px 이내) 그 그룹으로 귀속 (배경 잘림 방지)
        if not assigned and best_bg_idx != -1 and min_dist < 50:
            sections[best_bg_idx]['content'].append(l)
            assigned = True
            
        if not assigned:
            orphans.append(l)

    # 마지막에 orphans 섹션 추가
    if orphans:
        sections.append({'background': None, 'content': orphans})


    # --- 3단계: 섹션별 처리 및 스택킹 (Stacking) ---
    print("Step 3: Stacking sections...")
    final_layers = []
    current_stack_y = 0
    
    for section in sections:
        bg = section['background']
        content = section['content']
        
        if not bg and not content: continue
        
        # =================================================================
        # [추가 솔루션] 2단 컬럼(좌우 배치) 상단 정렬 강제 보정 로직
        # "텍스트가 이미지 옆에 있는데, 이유 없이 내려가 있다면 끌어올린다"
        # =================================================================
        if content:
            # 1. 이미지와 텍스트를 분리
            imgs = [l for l in content if l.get('type') == 'image']
            txts = [l for l in content if l.get('type') == 'text']
            
            for txt in txts:
                txt_x = txt.get('x', 0)
                txt_w = txt.get('width', 0)
                txt_y = txt.get('y', 0)
                
                # 가장 가까운 왼편/오른편 이미지를 찾음
                target_img = None
                
                for img in imgs:
                    img_x = img.get('x', 0)
                    img_w = img.get('width', 0)
                    img_y = img.get('y', 0)
                    
                    # A. X축이 겹치지 않아야 함 (진정한 좌우 배치)
                    is_x_overlap = not (txt_x >= img_x + img_w or txt_x + txt_w <= img_x)
                    
                    if not is_x_overlap:
                        # B. Y축 차이가 "애매하게" 나는 경우 (예: 0px ~ 250px 차이)
                        # 너무 멀리 떨어져 있으면(300px 이상) 다른 행일 수 있으므로 건드리지 않음
                        y_diff = txt_y - img_y
                        if 0 < y_diff < 250:
                            # C. 텍스트를 이미지의 상단 라인(Y)에 강제로 맞춤!
                            txt['y'] = img_y
                            # 로그 확인용 (필요시 주석 해제)
                            # print(f"Fixed: Text aligned to Image (gap was {y_diff})")
                            
        # =================================================================

        # 3-A. 섹션 내부 좌표 정규화 (Normalize to 0)
        # 섹션의 시작 Y를 0으로 맞추고 계산 시작
        section_start_y = bg.get('y', 0) if bg else (content[0].get('y', 0) if content else 0)
        
        if bg: 
            bg['y'] = 0 # 배경은 일단 0에서 시작
            
        # 콘텐츠들의 Y를 0 기준으로 변경 (상대 좌표)
        # + 이미지 리사이징에 따른 Shift 적용
        shrunk_images = [l for l in content if l.get('_height_diff', 0) > 0]
        
        for l in content:
            # 1. 상대 좌표로 변환
            rel_y = l.get('y', 0) - section_start_y
            
            # 2. 스마트 시프트 (이미지 줄어듦 반영)
            shift = 0
            for img in shrunk_images:
                # 내 위에 있는 이미지가 줄어들었다면 그만큼 당김
                # (원본 절대좌표 기준으로 비교해야 정확함)
                if l['_original_y'] > img['_original_y'] + (img['_original_height'] * 0.3):
                    shift += img['_height_diff']
            
            l['y'] = max(0, rel_y - shift)
            
            # 3. 꽉 찬 이미지인지 체크 (나중에 배경 여백 뺄 때 사용)
            if l.get('type') == 'image' and l.get('width', 0) >= (CANVAS_WIDTH - 10):
                if bg: bg['_has_full_img'] = True

        # 3-B. 충돌 해결 및 높이 확정 (Resolve Collisions)
        # ✅ 순서 지키기 로직이 적용된 함수 호출
        content_height = _resolve_collisions_preserving_order(content)
        
        # 3-C. 배경(Shape) 높이 및 섹션 최종 높이 결정
        section_height = 0
        padding = DEFAULT_PADDING
        
        if bg:
            if bg.get('_has_full_img'): padding = 0 # 꽉 찬 이미지 있으면 여백 0
            
            if content_height > 0:
                # 배경 높이는 콘텐츠를 감싸도록 늘리거나 줄임
                bg['height'] = content_height + padding
            else:
                # 콘텐츠 없는 배경(도입부 등)은 높이 유지하되 최대 300 제한
                orig_h = bg.get('_original_height', 0)
                bg['height'] = min(orig_h, 300) if orig_h > 0 else DEFAULT_PADDING
            
            section_height = bg['height']
        else:
            section_height = content_height + padding

        # 3-D. 스택킹 (최종 배치)
        # 현재까지 쌓인 높이(current_stack_y)에 섹션을 붙임
        if bg:
            bg['y'] += current_stack_y
            final_layers.append(bg)
            
        for l in content:
            l['y'] += current_stack_y
            # 이미지 중앙 정렬 (옵션)
            if l.get('type') == 'image' and bg and not bg.get('_has_full_img'):
                 if l['height'] < bg['height']:
                     # center_y = bg['y'] + (bg['height'] - l['height']) // 2
                     # 이미지가 텍스트와 겹치지 않을 때만 중앙 정렬 (단순화)
                     # 여기서는 안전하게 원래 계산된 위치(충돌해결됨)를 유지하는게 나을 수 있음
                     pass 
            final_layers.append(l)
            
        # 다음 섹션을 위해 스택 높이 갱신
        current_stack_y += section_height
        
        # 섹션 간 여백 추가 (너무 딱 붙지 않게)
        if bg and bg.get('_has_full_img'):
            pass # 이미지 배경끼리는 딱 붙임
        else:
            current_stack_y += 0 # 필요시 섹션 간 간격 추가

    # --- 4. 마무리 ---
    # 최종적으로 한 번 더 정렬 (안전장치)
    final_layers.sort(key=lambda l: (l.get('y', 0), l.get('zIndex', 0)))
    
    layout_data['layers'] = final_layers
    layout_data['canvas']['height'] = int(current_stack_y + DEFAULT_PADDING)
    
    print("--- Validator: Validation complete. ---")
    return layout_data