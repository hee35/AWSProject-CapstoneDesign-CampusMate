# CampusMate - [Notion Portfolio](https://kimheejoo.notion.site/capstonedesign)

- `main.py`: Backend server (connected to Bedrock Claude 3.5 Sonnet)  
- `index.html`: Landing page (Start)  
- `register.html`: Register page  
- `login.html`: Login page  
- `mode_select.html`: Chat mode selection page  
- `friend.html`: Casual chat mode page
- `professional.html`: Professional chat mode page  

---
# Server: Python(FastAPI)

1. 회원가입
    
    ```
    def register_user(
    	request: Request,
    	username: str = Form(...),
    	password: str = Form(...),
    	nickname: str = Form(...)
    )
    ```
    
    1. MySQL 데이터베이스 연결
    2. 사용자 정보 입력 받아 INSERT
    3. 성공 화면 반환 or 이미 존재하는 아이디일 경우 안내
2. 로그인
    
    ```python
    def login_process(
    	request: Request, 
    	username: str = Form(...), 
    	password: str = Form(...)
    )
    ```
    
    1. MySQL 데이터베이스 연결
    2. 입력 받은 사용자 정보 조회
    3. 성공 화면 반환 or 사용자 정보가 없거나 비밀번호 불일치 시 실패 처리
3. 채팅
    
    ```python
    def chat(
    	request: Request, 
    	user_input: str = Form(...), 
    	prompt_type: str = Path(...)
    )
    ```
    
    1. Claude 3.5 Sonnet API 호출
        
        `invoke_model(model_id, user_input, prompt_type, messages)`
        
        1. `prompt_type`에 맞는 `system_prompt` 와 `temperature` 설정
            - `friend`
                - `system_prompt` : 당신은 국민대학교 경영정보학과 선배이다. 친근하게 반말을 사용하여 대화하라. 모르는 것을 알기 쉽게 풀어서 설명해주고 고민이 있다면 들어주어라.
                - `temperature` : 0.7  (창의적/자연스러운 응답)
            - `professional`
                - `system_prompt` : 당신은 국민대학교 학사 전문가이다. 다음 교육과정 정보를 바탕으로 정확하게 답변하라:
                    `{rag_context}`
                    답변 시 다음 사항을 준수하라:
                    - 제공된 교육과정 정보 내에서만 답변
                    - 정보가 불충분하면 솔직히 "해당 정보가 부족합니다"라고 답변
                    - 유사도가 낮은 정보(0.7 미만)는 신중하게 사용
                    - 항상 존댓말 사용
                - `temperature` : 0.1  (정확하고 일관된 답변)
        2. 대화 기록(`messages`)에 현재 질문 추가
        3. API 호출
            
            ```python
            payload = {
                  "anthropic_version": "bedrock-2023-05-31",
                  "max_tokens": 800,
                  "system": system_prompt,
                  "temperature": temperature,
                  "messages": messages #이전 대화 + 현재 질문
              }
            ```
            
    2. 새로운 답변 대화 기록(`messages`)에 추가
    3. 대화 결과 포함된 채팅 화면 반환
4. 초기화 
    
    ```python
    def reset_chat(
    	request: Request, 
    	prompt_type: str = Form(...)
    )
    ```
    
    1. 대화 기록 초기화
    2. 채팅 화면 재연결
