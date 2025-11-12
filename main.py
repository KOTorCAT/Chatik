from fastapi import FastAPI, Request, Depends, HTTPException, WebSocket, WebSocketDisconnect, Form, status, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from jose import JWTError, jwt
import hashlib
import json
import asyncio
import os
import shutil
from typing import List, Dict
from pathlib import Path

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat_app.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship with messages
    messages = relationship("Message", back_populates="user")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    room = Column(String(50), default="general")
    
    # File fields
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(String(50), nullable=True)
    file_type = Column(String(50), nullable=True)  # 'image', 'video', 'file'
    
    # Relationship with user
    user = relationship("User", back_populates="messages")

# Create tables
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(title="Enterprise Chat")

# Create upload directories
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "images").mkdir(exist_ok=True)
(UPLOAD_DIR / "videos").mkdir(exist_ok=True)
(UPLOAD_DIR / "files").mkdir(exist_ok=True)

# Templates and static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Auth
SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password, hashed_password):
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple session management
logged_in_users = {}

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise credentials_exception
        return user
    finally:
        db.close()

# WebSocket manager for multiple users
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {"general": []}
        self.user_rooms: Dict[str, str] = {}  # username -> room

    async def connect(self, websocket: WebSocket, username: str, room: str = "general"):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        self.user_rooms[username] = room
        
        # Notify everyone that user joined
        await self.broadcast_json({
            "type": "user_joined",
            "username": username,
            "message": f"{username} joined the chat",
            "timestamp": datetime.now().isoformat(),
            "online_users": self.get_online_users(room)
        }, room)

    def disconnect(self, websocket: WebSocket, username: str):
        room = self.user_rooms.get(username, "general")
        if room in self.active_connections and websocket in self.active_connections[room]:
            self.active_connections[room].remove(websocket)
        
        if username in self.user_rooms:
            del self.user_rooms[username]
        
        # Notify everyone that user left
        asyncio.create_task(self.broadcast_json({
            "type": "user_left",
            "username": username,
            "message": f"{username} left the chat",
            "timestamp": datetime.now().isoformat(),
            "online_users": self.get_online_users(room)
        }, room))

    async def broadcast_json(self, message: dict, room: str):
        if room in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room]:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    disconnected.append(connection)
            
            # Remove disconnected clients
            for connection in disconnected:
                self.active_connections[room].remove(connection)

    async def broadcast_message(self, message_data: dict, room: str = "general"):
        await self.broadcast_json({
            "type": "new_message",
            "message": message_data
        }, room)

    def get_online_users(self, room: str = "general"):
        online_users = []
        for username, user_room in self.user_rooms.items():
            if user_room == room:
                online_users.append(username)
        return online_users

    def get_room_for_user(self, username: str):
        return self.user_rooms.get(username, "general")

manager = ConnectionManager()

# Routes
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/chat")
async def chat_page(request: Request):
    # Try token-based auth first
    token = request.query_params.get("token")
    user = None
    
    if token:
        try:
            user = get_current_user(token)
        except:
            pass
    
    # Fallback to cookie-based auth
    if not user:
        username = request.cookies.get("username")
        if username and username in logged_in_users:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.username == username).first()
            finally:
                db.close()
    
    # If no valid user, redirect to login
    if not user:
        return RedirectResponse(url="/login")
    
    db = SessionLocal()
    try:
        # Get last 50 messages with user relationship
        messages = db.query(Message).join(User).order_by(Message.created_at.desc()).limit(50).all()
        messages.reverse()
        
        # Get online users
        online_users = manager.get_online_users()
        
        return templates.TemplateResponse("chat.html", {
            "request": request, 
            "user": user,
            "messages": messages,
            "online_users": online_users
        })
    finally:
        db.close()

@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            raise HTTPException(status_code=400, detail="Username или email уже заняты")
        
        hashed_password = get_password_hash(password)
        db_user = User(
            username=username,
            email=email,
            hashed_password=hashed_password
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return {"message": "Регистрация успешна! Теперь войдите."}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")
    finally:
        db.close()

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Неверный username или пароль")
        
        # Create token
        access_token = create_access_token(data={"sub": user.username})
        
        # Also store in simple session for fallback
        logged_in_users[username] = True
        
        response = JSONResponse({
            "access_token": access_token,
            "token_type": "bearer",
            "username": user.username,
            "message": "Вход успешен!"
        })
        
        # Set cookie for session fallback
        response.set_cookie(
            key="username",
            value=username,
            httponly=True,
            max_age=3600
        )
        
        return response
        
    finally:
        db.close()

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("username")
    return response

@app.get("/online-users")
async def get_online_users():
    return {"online_users": manager.get_online_users()}

# API endpoints for messages
@app.get("/api/messages")
async def get_recent_messages():
    db = SessionLocal()
    try:
        messages = db.query(Message).join(User).order_by(Message.created_at.desc()).limit(50).all()
        messages.reverse()
        
        return [{
            "id": msg.id,
            "content": msg.content,
            "username": msg.user.username,
            "user_id": msg.user_id,
            "created_at": msg.created_at.isoformat(),
            "file_url": msg.file_url,
            "file_name": msg.file_name,
            "file_size": msg.file_size,
            "file_type": msg.file_type
        } for msg in messages]
    finally:
        db.close()

@app.post("/api/messages")
async def create_message(
    request: Request,
    message_data: dict
):
    # Get user from cookie
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        db_message = Message(
            content=message_data["content"],
            user_id=user.id
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        # Broadcast via WebSocket
        room = manager.get_room_for_user(username)
        await manager.broadcast_message({
            "id": db_message.id,
            "content": message_data["content"],
            "username": username,
            "user_id": user.id,
            "created_at": db_message.created_at.isoformat(),
            "room": room,
            "file_url": None,
            "file_name": None,
            "file_size": None,
            "file_type": None
        }, room)
        
        return {"status": "ok", "message_id": db_message.id}
    finally:
        db.close()

# File upload endpoint
@app.post("/api/upload")
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    content: str = Form(None),
    db: Session = Depends(get_db)
):
    username = request.cookies.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    try:
        uploaded_messages = []
        
        for file in files:
            # Determine file type
            if file.content_type and file.content_type.startswith('image/'):
                file_type = 'image'
                subdir = 'images'
            elif file.content_type and file.content_type.startswith('video/'):
                file_type = 'video'
                subdir = 'videos'
            else:
                file_type = 'file'
                subdir = 'files'
            
            # Generate unique filename
            file_extension = Path(file.filename).suffix
            unique_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{file.filename}"
            file_path = UPLOAD_DIR / subdir / unique_filename
            
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Create database record
            db_message = Message(
                content=content or f"Sent a {file_type}",
                user_id=user.id,
                file_url=f"/static/uploads/{subdir}/{unique_filename}",
                file_name=file.filename,
                file_size=str(file_path.stat().st_size),
                file_type=file_type
            )
            db.add(db_message)
            uploaded_messages.append(db_message)
        
        db.commit()
        
        # Refresh to get IDs
        for message in uploaded_messages:
            db.refresh(message)
        
        # Broadcast via WebSocket
        room = manager.get_room_for_user(username)
        for message in uploaded_messages:
            await manager.broadcast_message({
                "id": message.id,
                "content": message.content,
                "username": username,
                "user_id": user.id,
                "created_at": message.created_at.isoformat(),
                "room": room,
                "file_url": message.file_url,
                "file_name": message.file_name,
                "file_size": message.file_size,
                "file_type": message.file_type
            }, room)
        
        return {"status": "success", "message": "Files uploaded successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error uploading files: {str(e)}")

# PUT endpoint for editing messages
@app.put("/api/messages/{message_id}")
async def update_message(
    message_id: int,
    message_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # Get current user from cookie
        username = request.cookies.get("username")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Find message
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        # Check if user owns the message
        if message.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only edit your own messages"
            )
        
        # Update message content
        message.content = message_data["content"]
        db.commit()
        
        # Broadcast update via WebSocket
        room = manager.get_room_for_user(username)
        await manager.broadcast_json({
            "type": "message_updated",
            "message": {
                "id": message.id,
                "content": message.content,
                "username": username,
                "user_id": user.id,
                "created_at": message.created_at.isoformat(),
                "room": room,
                "file_url": message.file_url,
                "file_name": message.file_name,
                "file_size": message.file_size,
                "file_type": message.file_type
            }
        }, room)
        
        return {"status": "success", "message": "Message updated"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating message: {str(e)}"
        )

# DELETE endpoints for messages
@app.delete("/api/messages/{message_id}")
async def delete_message(
    message_id: int, 
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # Get current user from cookie
        username = request.cookies.get("username")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Find message
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        # Check if user owns the message
        if message.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only delete your own messages"
            )
        
        # Delete associated file if exists
        if message.file_url:
            file_path = message.file_url.replace('/static/', 'static/')
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete message
        db.delete(message)
        db.commit()
        
        # Broadcast deletion via WebSocket
        room = manager.get_room_for_user(username)
        await manager.broadcast_json({
            "type": "message_deleted",
            "message_id": message_id
        }, room)
        
        return {
            "status": "success", 
            "message": "Message deleted",
            "deleted_id": message_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting message: {str(e)}"
        )

@app.delete("/api/messages")
async def clear_all_messages(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # Get current user from cookie
        username = request.cookies.get("username")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Get user's messages with files first to delete files
        user_messages = db.query(Message).filter(Message.user_id == user.id).all()
        
        # Delete associated files
        for message in user_messages:
            if message.file_url:
                file_path = message.file_url.replace('/static/', 'static/')
                if os.path.exists(file_path):
                    os.remove(file_path)
        
        # Delete only user's messages
        deleted_count = db.query(Message).filter(Message.user_id == user.id).delete()
        db.commit()
        
        return {
            "status": "success", 
            "message": f"Deleted {deleted_count} messages",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing messages: {str(e)}"
        )

# Debug endpoint to see all messages
@app.get("/api/debug/messages")
async def debug_messages(db: Session = Depends(get_db)):
    """Endpoint для отладки - показывает все сообщения"""
    messages = db.query(Message).join(User).all()
    return [
        {
            "id": msg.id,
            "content": msg.content,
            "username": msg.user.username,
            "user_id": msg.user_id,
            "created_at": msg.created_at.isoformat(),
            "file_url": msg.file_url,
            "file_name": msg.file_name,
            "file_size": msg.file_size,
            "file_type": msg.file_type
        } for msg in messages
    ]

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "message":
                content = message_data.get("content", "").strip()
                if content:
                    db = SessionLocal()
                    try:
                        user = db.query(User).filter(User.username == username).first()
                        if user:
                            db_message = Message(
                                content=content,
                                user_id=user.id
                            )
                            db.add(db_message)
                            db.commit()
                            db.refresh(db_message)
                            
                            room = manager.get_room_for_user(username)
                            await manager.broadcast_message({
                                "id": db_message.id,
                                "content": content,
                                "username": username,
                                "user_id": user.id,
                                "created_at": db_message.created_at.isoformat(),
                                "room": room,
                                "file_url": None,
                                "file_name": None,
                                "file_size": None,
                                "file_type": None
                            }, room)
                    finally:
                        db.close()
                        
            # Handle WebSocket events for real-time updates
            elif message_data.get("type") == "message_updated":
                # This would be handled by the HTTP API, but we can broadcast
                room = manager.get_room_for_user(username)
                await manager.broadcast_json(message_data, room)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, username)

# Add test users on startup
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    try:
        # Add test users if they don't exist
        test_users = [
            ("alex", "alex@example.com", "password123"),
            ("maria", "maria@example.com", "password123"),
            ("john", "john@example.com", "password123")
        ]
        
        for username, email, password in test_users:
            existing_user = db.query(User).filter(User.username == username).first()
            if not existing_user:
                hashed_password = get_password_hash(password)
                user = User(
                    username=username,
                    email=email,
                    hashed_password=hashed_password
                )
                db.add(user)
                print(f"✅ Создан тестовый пользователь: {username}")
        
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)