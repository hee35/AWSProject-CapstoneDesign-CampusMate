from fastapi import FastAPI, Form, Request, Path
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
import boto3
import json
import pymysql
import psycopg2
import re

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
messages = []

def get_user_db():
  return pymysql.connect(
    host="mis.cluster-cml64gigeh1t.us-east-1.rds.amazonaws.com",
    user="user1",
    password="password123",
    database="user_db",
    autocommit=True
  )

#MySQL
def get_mis_db():
  return pymysql.connect(
    host="mis.cluster-cml64gigeh1t.us-east-1.rds.amazonaws.com",
    user="user",
    password="password123",
    database="mis_db",
    autocommit=True
  )

#PostgreSQL
def get_pg_conn():
  return psycopg2.connect(
    host="campus-mate.cluster-cml64gigeh1t.us-east-1.rds.amazonaws.com",
    user="postgres",
    password="campusmate2025",
    database="campus-mate"
  )

#임베딩 모델 호출
def get_embedding(text: str) -> list[float]:
    body = {
      "inputText": text,
      "dimensions": 512, # 선택 가능한 값: 256, 512, 1024
      "normalize": True # 벡터 정규화 여부
    }
    try:
      response = bedrock_client.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
      )
      result = json.loads(response['body'].read())
      return result["embedding"]
    except Exception as e:
      print(f"[Embedding Error] {str(e)}")
      return []

def build_content(row):
    admission_year, grade, semester, category, subject, credit, prerequisite, note, major, summary = row

    content_parts = []
    
    # 기본 과목 정보를 자연어로 구성
    content_parts.append(f"{major} {admission_year}에 입학한 학생의 졸업 요건입니다.")
    content_parts.append(f"{grade}학년 {semester} {category} 과목인 {subject}는 {credit}학점입니다.")
    content_parts.append(f"필수 여부: {note}")
    
    # summary와 note는 NULL일 수 있으므로 처리 필요
    def handle_null(value):
        return "없음" if value is None or value == "NULL" or value == "" else value
    
    # 과목 설명 (NULL 처리 필요)
    summary_text = handle_null(summary)
    content_parts.append(f"{subject} 과목 설명: {summary_text}")
    
    # 선수과목 정보 (DB에서 이미 "없음"으로 처리됨)  
    if prerequisite == "없음":
        content_parts.append(f"{subject}는 선수과목이 없어 자유롭게 수강할 수 있습니다.")
    else:
        content_parts.append(f"{subject}의 선수과목은 {prerequisite}입니다.")
    
    # 검색 키워드 추가 (임베딩 성능 향상을 위해)
    keywords = []
    keywords.append(f"학번:{admission_year}")
    keywords.append(f"학년:{grade}")
    keywords.append(f"학기:{semester}")  
    keywords.append(f"분류:{category}")
    keywords.append(f"과목:{subject}")
    keywords.append(f"학점:{credit}")
    keywords.append(f"필수 여부:{note}")
    keywords.append(f"선수과목:{prerequisite}")
    keywords.append(f"설명:{summary_text}") # NULL 처리 후 사용
    
    content_parts.append(f"검색키워드: {', '.join(keywords)}")
    
    return " ".join(content_parts)

# 마이그레이션 함수 (embedding 없이 content만)
def migrate():
    mysql_conn = get_mis_db()
    mysql_cursor = mysql_conn.cursor()
    # 필요한 컬럼만 선택 (build_content 인자에 맞게)
    mysql_cursor.execute("""
      SELECT 
        gr.admission_year, gr.grade, gr.semester, gr.category, gr.subject, 
        gr.credit, gr.prerequisite, gr.note, gr.major, c.summary
      FROM graduation_requirements gr
      LEFT JOIN courses c ON gr.subject = c.name;
    """)
    rows = mysql_cursor.fetchall()
    mysql_conn.close()

    pg_conn = get_pg_conn()
    pg_cursor = pg_conn.cursor()
    

    for idx, row in enumerate(rows, start=1):  # id는 1부터 순서대로 부여
        content = build_content(row)

        pg_cursor.execute("""
            INSERT INTO documents (id, content)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (idx, content))

    pg_conn.commit()
    pg_conn.close()

# 임베딩 업데이트 함수
def update_embeddings():
    pg_conn = None
    try:
        pg_conn = get_pg_conn()
        pg_cursor = pg_conn.cursor()

        pg_cursor.execute("SELECT id, content FROM documents WHERE embedding IS NULL")
        docs = pg_cursor.fetchall()

        for doc_id, content in docs:
            embedding = get_embedding(content)
            if embedding:  # 임베딩이 성공적으로 생성된 경우에만 업데이트
                vector_str = '[' + ','.join(map(str, embedding)) + ']'

                pg_cursor.execute("""
                    UPDATE documents SET embedding = %s::vector WHERE id = %s
                """, (vector_str, doc_id))

        pg_conn.commit()
        print(f"Embeddings updated for {len(docs)} documents")
        
    except Exception as e:
        print(f"[Embedding Update Error] {str(e)}")
    finally:
        if pg_conn:
            pg_conn.close()

@app.on_event("startup")
async def startup_event():
    migrate()
    update_embeddings() 


# 하이브리드 검색 함수 (벡터 + 키워드 검색)
def search_similar_documents(query: str, top_k: int = 5) -> list[dict]:
    try:
        # 벡터 검색
        query_embedding = get_embedding(query)
        if not query_embedding:
            return []
        
        pg_conn = get_pg_conn()
        pg_cursor = pg_conn.cursor()
        
        # 쿼리에서 키워드 추출
        grade_match = re.search(r'(\d+)학년', query)
        semester_match = re.search(r'(\d+)학기', query)
        category_keywords = ['전공필수', '전공선택', '기초교양', '핵심교양']
        found_category = None
        for cat in category_keywords:
            if cat in query:
                found_category = cat
                break
        
        # 하이브리드 검색 쿼리 구성
        vector_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # 필터링 조건 추가
        where_conditions = ["embedding IS NOT NULL"]
        params = [vector_str, vector_str]
        
        if grade_match:
            where_conditions.append("content LIKE %s")
            params.append(f"%{grade_match.group(1)}학년%")
            
        if semester_match:
            where_conditions.append("content LIKE %s") 
            params.append(f"%{semester_match.group(1)}학기%")
            
        if found_category:
            where_conditions.append("content LIKE %s")
            params.append(f"%{found_category}%")
        
        where_clause = " AND ".join(where_conditions)
        params.append(top_k)
        
        query_sql = f"""
            SELECT id, content, 1 - (embedding <=> %s::vector) as similarity
            FROM documents 
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        
        pg_cursor.execute(query_sql, params)
        results = pg_cursor.fetchall()
        pg_conn.close()
        
        documents = []
        for doc_id, content, similarity in results:
            documents.append({
                'id': doc_id,
                'content': content,
                'similarity': float(similarity)
            })
        
        return documents
        
    except Exception as e:
        print(f"[Hybrid Search Error] {str(e)}")
        return []

# 개선된 컨텍스트 빌더
def build_rag_context(documents: list[dict]) -> str:
    if not documents:
        return "관련 정보를 찾을 수 없습니다."
    
    # 유사도 기준으로 필터링
    high_similarity_docs = [doc for doc in documents if doc['similarity'] > 0.7]
    medium_similarity_docs = [doc for doc in documents if 0.5 <= doc['similarity'] <= 0.7]
    
    context = ""
    
    if high_similarity_docs:
        context += "관련성이 높은 교육과정 정보:\n"
        for i, doc in enumerate(high_similarity_docs, 1):
            context += f"{i}. {doc['content']}\n"
        context += "\n"
    
    if medium_similarity_docs:
        context += "참고할 만한 추가 정보:\n"
        for i, doc in enumerate(medium_similarity_docs, 1):
            context += f"{i}. {doc['content']}\n"
        context += "\n"
    
    return context

def invoke_model(model_id: str, user_input: str, prompt_type: str, messages: list[dict[str, str]]) -> str:
  
  # 벡터 검색으로 관련 문서 찾기
  relevant_docs = search_similar_documents(user_input, top_k=3)
  rag_context = build_rag_context(relevant_docs)
  # Prompt와 temperature를 prompt_type에 따라 정의
  if prompt_type == "friend":
    system_prompt = """당신은 국민대학교 경영정보학과 선배이다. 친근하게 반말을 사용하여 대화하라. 모르는 것을 알기 쉽게 풀어서 설명해주고 고민이 있다면 들어주어라."""
    temperature = 0.7  #창의적/자연스러운 응답
  else:
    system_prompt = """당신은 국민대학교 경영정보학과 학사 전문가이다. 다음의 정보를 바탕으로 학생의 학사 문의에 정확하게 답변하라. 정확한 정보 조회를 위해 학생의 정보가 필요하다면 요구하라.:
    {rag_context}
    답변 시 다음 사항을 준수하라:
    - 제공된 정보 내에서만 답변
    - 정보가 불충분하면 솔직히 "해당 정보가 부족합니다"라고 답변
    - 유사도가 낮은 정보(0.7 미만)는 신중하게 사용
    - 항상 존댓말 사용
    """.format(rag_context=rag_context)
    temperature = 0.1  #정확하고 일관된 답변

  messages.append({"role": "user", "content": user_input}) #현재 질문 추가

  payload = {
      "anthropic_version": "bedrock-2023-05-31",
      "max_tokens": 800,
      "system": system_prompt,
      "temperature": temperature,  #동적으로 설정된 temperature 사용
      "messages": messages #이전 대화 + 현재 질문
  }

  try:
    # Bedrock API 호출
    response = bedrock_client.invoke_model(
        modelId=model_id,
        contentType='application/json',
        accept='application/json',
        body=json.dumps(payload)
    )
    # 응답 처리
    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text']  # 최종 응답 반환
  except Exception as e:
    print(f"[Error] {str(e)}")  # 로그 출력
    return "잠시 후에 다시 시도해 주세요."

# Bedrock 클라이언트 설정
bedrock_client = boto3.client(
  'bedrock-runtime',
  region_name='us-east-1'
)

#첫 화면
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
  return templates.TemplateResponse("index.html", {"request": request})

#회원가입 화면
@app.get("/register", response_class=HTMLResponse)
async def index(request: Request):
  return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
def register_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    nickname: str = Form(...)
):
    conn = None
    try:
        # MySQL 데이터베이스 연결
        conn = get_user_db()
        # 사용자 정보 INSERT 실행
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password, nickname) VALUES (%s, %s, %s)",
                (username, password, nickname)
            )
        # 회원가입 성공 메시지 반환
        return HTMLResponse(content="<h3>회원가입 성공! <a href='/login'>로그인</a></h3>")

    # 이미 존재하는 사용자 처리 (중복 아이디)
    except pymysql.err.IntegrityError:
        return HTMLResponse(content="<h3>이미 존재하는 아이디입니다.</h3>", status_code=400)

    # 기타 MySQL 오류 처리
    except pymysql.MySQLError as e:
        return HTMLResponse(content=f"<h3>DB 오류: {e}</h3>", status_code=500)

    # 커넥션이 존재할 경우 반드시 닫아줌
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
            
#로그인 화면
@app.get("/login", response_class=HTMLResponse)
async def index(request: Request):
  return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login_process(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = None
    try:
        # MySQL 데이터베이스 연결
        conn = get_user_db()
        # 커서 열고 사용자 정보 조회
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, password, nickname FROM users WHERE username = %s",
                (username,)
            )
            user = cursor.fetchone()

            # 사용자 정보가 없거나 비밀번호 불일치 시 실패 처리
            if not user or user[1] != password:
                return HTMLResponse(content="<h3>로그인 실패: 아이디 또는 비밀번호가 틀렸습니다.</h3>", status_code=401)

            # 로그인 성공 시
            return templates.TemplateResponse("mode_select.html", {"request": request,"nickname": user[2]})
        
    # DB 연결 오류 처리
    except pymysql.MySQLError as e:
        return HTMLResponse(content=f"<h3>DB 연결 오류: {str(e)}</h3>", status_code=500)

    # 커넥션이 존재할 경우 반드시 닫아줌
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
            
@app.post("/reset", response_class=HTMLResponse)
async def reset_chat(request: Request, prompt_type: str = Form(...)):
  global messages
  messages.clear() #대화 기록 초기화
  return RedirectResponse(url=f"/{prompt_type}", status_code=303)

#채팅 화면
@app.get("/{prompt_type}", response_class=HTMLResponse)
async def prompt_type(request: Request, prompt_type: str):
  global messages
  messages.clear() #대화 기록 초기화
  if prompt_type == "friend":
    return templates.TemplateResponse("friend.html", 
    {"request": request, "prompt_type": prompt_type, "chat_history": messages, "user_input": "", "response": ""})
  elif prompt_type == "professional":
    return templates.TemplateResponse("professional.html", {"request": request, "prompt_type": prompt_type, "chat_history": messages, "user_input": "", "response": ""})
  else:
    return HTMLResponse("Invalid prompt_type", status_code=400)

@app.post("/{prompt_type}", response_class=HTMLResponse)
async def chat(request: Request, user_input: str = Form(...), prompt_type: str = Path(...)):
  global messages
  model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"

  response = invoke_model(model_id, user_input, prompt_type, messages)
  messages.append({"role": "assistant", "content": response})

  return templates.TemplateResponse(f"{prompt_type}.html", {
      "request": request,
      "response": response,
      "user_input": user_input,
      "prompt_type": prompt_type,
      "chat_history": messages # 갱신된 채팅 기록을 전달
  })


