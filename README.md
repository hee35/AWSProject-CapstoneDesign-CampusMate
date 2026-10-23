# CampusMate - [Notion Portfolio](https://kimheejoo.notion.site/capstonedesign)

- `main.py`: Backend server (connected to Bedrock Claude 3.5 Sonnet)  
- `index.html`: Landing page (Start)  
- `register.html`: Register page  
- `login.html`: Login page  
- `mode_select.html`: Chat mode selection page  
- `friend.html`: Casual chat mode page
- `professional.html`: Professional chat mode page  



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
  


# 벡터 DB 생성 과정

```python
@app.on_event("startup")
async def startup_event():
    migrate()
    update_embeddings() 
```

서버 시작 할 때마다 `migrate()`, `update_embeddings()` 실행

1. `def migrate()`
    1. `mis_db` 와 연결
    2. 사용할 컬럼만 선택하여 가져오기
    3. `campus-mate` 와 연결
    4. 벡터 db에 들어갈 포멧으로 변환
        
        ```python
        def build_content(row):
            admission_year, grade, semester, category, subject, credit, prerequisite, note, major = row
            return f"""
        전공: {major}
        과목명: {subject}
        기준 학번: {admission_year}
        학년/학기: {grade}학년 {semester}
        카테고리: {category}
        학점: {credit}
        설명: {note or '없음'}
        선수과목: {prerequisite or '없음'}
        """
        ```
        
    5. `campus-mate`에 INSERT
2. `def update_embeddings()`
    1. `campus-mate` 와 연결
    2. 임베딩 안된 행만 선택
    3. 벡터로 변환: 임베딩 모델 호출(Titan Text Embeddings V2)
        
        ```
        def get_embedding(text: str) -> list[float]:
            body = {
              "inputText": text,
              "dimensions": 512, # 선택 가능한 값: 256, 512, 1024
              "normalize": True # 벡터 정규화 여부
            }
        ```
        
    4. 임베딩 성공한 경우 UPDATE



# 벡터 DB 검색 과정 `{rag_context}`

1. 벡터 검색으로 관련 문서 찾기 `def search_similar_documents`
    1. 질문을 임베딩으로 변환(Titan Text Embeddings V2)
    2. PostgreSQL에서 벡터 유사도 검색
    3. 결과를 딕셔너리 형태로 변환 하여 전달
2. 검색된 문서들 정리하여 전달 `def build_rag_context`
    - 검색된 문서 없는 경우: "관련 정보를 찾을 수 없습니다.”
    - 검색된 문서 있는 경우: 챗봇에 내용 전달


  
# DB: RDS Aurora

- MySQL
    - `user_db` : 사용자 데이터
        - 로그인 정보 테이블
            
            ```sql
            DESCRIBE users;
            +----------+--------------+------+-----+---------+----------------+
            | Field    | Type         | Null | Key | Default | Extra          |
            +----------+--------------+------+-----+---------+----------------+
            | id       | int          | NO   | PRI | NULL    | auto_increment |
            | username | varchar(100) | NO   | UNI | NULL    |                |
            | password | varchar(255) | NO   |     | NULL    |                |
            | nickname | varchar(100) | NO   |     | NULL    |                |
            +----------+--------------+------+-----+---------+----------------+
            ```
            
        - 채팅 기록 테이블
            
            ```sql
            DESCRIBE chat_messages;
            +-------------+-----------------+------+-----+-------------------+-------------------+
            | Field       | Type            | Null | Key | Default           | Extra             |
            +-------------+-----------------+------+-----+-------------------+-------------------+
            | id          | bigint unsigned | NO   | PRI | NULL              | auto_increment    |
            | user_id     | varchar(255)    | NO   |     | NULL              |                   |
            | role        | varchar(10)     | NO   |     | NULL              |                   |
            | content     | text            | NO   |     | NULL              |                   |
            | prompt_type | varchar(50)     | YES  |     | NULL              |                   |
            | created_at  | timestamp       | YES  |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
            +-------------+-----------------+------+-----+-------------------+-------------------+
            ```
            
    - `mis_db`: 학사 정보 데이터
        - 졸업 요건 테이블
            
            ```sql
            DESCRIBE graduation_requirements;
            +----------------+--------------+------+-----+---------+----------------+
            | Field          | Type         | Null | Key | Default | Extra          |
            +----------------+--------------+------+-----+---------+----------------+
            | id             | int          | NO   | PRI | NULL    | auto_increment |
            | admission_year | year         | NO   |     | NULL    |                |
            | grade          | varchar(10)  | YES  |     | NULL    |                |
            | semester       | varchar(20)  | YES  |     | NULL    |                |
            | category       | varchar(50)  | YES  |     | NULL    |                |
            | subject        | varchar(255) | YES  |     | NULL    |                |
            | credit         | tinyint      | YES  |     | NULL    |                |
            | theory_design  | tinyint      | YES  |     | NULL    |                |
            | experiment     | tinyint      | YES  |     | NULL    |                |
            | prerequisite   | varchar(255) | YES  |     | NULL    |                |
            | note           | text         | YES  |     | NULL    |                |
            | major          | varchar(100) | YES  |     | NULL    |                |
            +----------------+--------------+------+-----+---------+----------------+
            ```
            
        - 과목 정보 테이블
            
            ```sql
            describe courses;
            +-------------+--------------+------+-----+---------+-------+
            | Field       | Type         | Null | Key | Default | Extra |
            +-------------+--------------+------+-----+---------+-------+
            | id          | int          | NO   | PRI | NULL    |       |
            | name        | varchar(100) | YES  |     | NULL    |       |
            | description | text         | YES  |     | NULL    |       |
            +-------------+--------------+------+-----+---------+-------+
            ```
            
- PostgreSQL
    - `campus-mate` : RAG 반영할 데이터
        - `mis_db` 의 데이터를 벡터로 변경한 테이블
            
            ```sql
            \d documents
                                                    Table "public.documents"
               Column   |            Type             | Collation | Nullable |                Default                
            ------------+-----------------------------+-----------+----------+---------------------------------------
             id         | integer                     |           | not null | nextval('documents_id_seq'::regclass)
             content    | text                        |           |          | 
             embedding  | vector(512)                 |           |          | 
             created_at | timestamp without time zone |           |          | now()
            Indexes:
                "documents_pkey" PRIMARY KEY, btree (id)
                "documents_embedding_idx" hnsw (embedding vector_cosine_ops)
            ```
            
