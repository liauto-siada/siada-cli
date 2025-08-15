#!/usr/bin/env python3
"""
压缩工具演示脚本

直接调用 _compress_context_tool 方法并展示压缩结果
"""

import asyncio
from typing import List

from siada.tools.compression_tool import _compress_context_tool
from siada.foundation.code_agent_context import CodeAgentContext
from agents.items import TResponseInputItem


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: CodeAgentContext):
        self.context = context


def create_demo_message_history() -> List[TResponseInputItem]:
    """创建演示用的消息历史"""
    return [
        {
            "role": "user", 
            "content": "请帮我创建一个Python Web API，使用FastAPI框架。"
        },
        {
            "role": "assistant", 
            "content": """我来帮您创建一个Python Web API，使用FastAPI框架：

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

app = FastAPI(title="Demo API", version="1.0.0")

class Item(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    price: float

# 模拟数据库
items_db = []

@app.get("/")
async def root():
    return {"message": "Welcome to Demo API"}

@app.get("/items", response_model=List[Item])
async def get_items():
    return items_db

@app.post("/items", response_model=Item)
async def create_item(item: Item):
    item.id = len(items_db) + 1
    items_db.append(item)
    return item

@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

这个API包含了基本的CRUD操作。"""
        },
        {
            "role": "user", 
            "content": "请添加数据验证和错误处理功能。"
        },
        {
            "role": "assistant", 
            "content": """我来为API添加更完善的数据验证和错误处理：

```python
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, Field
from typing import List, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Enhanced Demo API", version="2.0.0")

class Item(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price: float = Field(..., gt=0, description="Price must be greater than 0")
    category: str = Field(..., min_length=1, max_length=50)
    
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty or whitespace')
        return v.strip()

class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int

# 全局异常处理器
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": "Validation Error", "detail": str(exc), "status_code": 400}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTP Error", "detail": exc.detail, "status_code": exc.status_code}
    )

# 依赖注入：验证item存在
def get_item_by_id(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, 
        detail=f"Item with id {item_id} not found"
    )

@app.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(item: Item):
    try:
        item.id = len(items_db) + 1
        items_db.append(item)
        logger.info(f"Created item: {item.name}")
        return item
    except Exception as e:
        logger.error(f"Error creating item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create item"
        )

@app.put("/items/{item_id}", response_model=Item)
async def update_item(item_id: int, updated_item: Item, existing_item: Item = Depends(get_item_by_id)):
    try:
        existing_item.name = updated_item.name
        existing_item.description = updated_item.description
        existing_item.price = updated_item.price
        existing_item.category = updated_item.category
        logger.info(f"Updated item: {item_id}")
        return existing_item
    except Exception as e:
        logger.error(f"Error updating item {item_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update item"
        )
```

现在API具有完善的验证和错误处理机制。"""
        },
        {
            "role": "user", 
            "content": "请添加用户认证和权限管理功能。"
        },
        {
            "role": "assistant", 
            "content": """我来为API添加JWT用户认证和权限管理：

```python
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
import os

# JWT配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(title="Secure Demo API", version="3.0.0")

class User(BaseModel):
    id: Optional[int] = None
    username: str
    email: str
    role: str = "user"  # user, admin
    is_active: bool = True

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# 模拟用户数据库
users_db = [
    {
        "id": 1,
        "username": "admin",
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "role": "admin",
        "is_active": True
    }
]

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(username: str, password: str):
    for user in users_db:
        if user["username"] == username:
            if verify_password(password, user["hashed_password"]):
                return user
    return None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    for user in users_db:
        if user["username"] == username:
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found"
    )

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

@app.post("/register", response_model=User)
async def register(user: UserCreate):
    # 检查用户名是否已存在
    for existing_user in users_db:
        if existing_user["username"] == user.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
    
    new_user = {
        "id": len(users_db) + 1,
        "username": user.username,
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "role": "user",
        "is_active": True
    }
    users_db.append(new_user)
    
    return User(**{k: v for k, v in new_user.items() if k != "hashed_password"})

@app.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    user = authenticate_user(user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/profile", response_model=User)
async def get_profile(current_user: dict = Depends(get_current_user)):
    return User(**{k: v for k, v in current_user.items() if k != "hashed_password"})

@app.get("/admin/users", response_model=List[User])
async def get_all_users(admin_user: dict = Depends(get_admin_user)):
    return [User(**{k: v for k, v in user.items() if k != "hashed_password"}) for user in users_db]
```

现在API具有完整的JWT认证和基于角色的权限管理。"""
        }
    ]


async def main():
    """主演示函数"""
    print("🎯 压缩工具演示")
    print("=" * 60)
    
    # 创建测试数据
    message_history = create_demo_message_history()
    context = CodeAgentContext(root_dir="/demo/project")
    context.message_history = message_history
    wrapper = MockRunContextWrapper(context)
    
    print(f"\n📊 原始对话统计:")
    print(f"  - 总消息数: {len(message_history)}")
    total_chars = sum(len(msg['content']) for msg in message_history)
    print(f"  - 总字符数: {total_chars}")
    
    print(f"\n📝 原始对话内容:")
    for i, msg in enumerate(message_history):
        role = msg["role"]
        content = msg["content"][:120] + "..." if len(msg["content"]) > 120 else msg["content"]
        print(f"  [{i}] {role}: {content}")
    
    # 执行压缩
    print(f"\n🚀 开始压缩...")
    reason = "演示压缩功能：将FastAPI开发对话压缩为简洁摘要"
    start_index = 1
    end_index = 5
    
    print(f"\n📋 压缩参数:")
    print(f"  - 压缩原因: {reason}")
    print(f"  - 压缩范围: 索引 {start_index} 到 {end_index-1}")
    
    result = await _compress_context_tool(
        context=wrapper,
        reason=reason,
        start_index=start_index,
        end_index=end_index
    )
    
    # 展示结果
    print(f"\n✅ 压缩结果:")
    print(f"  - 状态: {'成功' if result['status'] == 1 else '失败'}")
    print(f"  - 起始索引: {result['start_index']}")
    print(f"  - 结束索引: {result['end_index']}")
    
    if result['status'] == 1:
        summary = result['summary']
        print(f"  - 摘要长度: {len(summary)} 字符")
        
        # 计算压缩效果
        original_length = sum(len(msg["content"]) for msg in message_history[start_index:end_index])
        compressed_length = len(summary)
        compression_ratio = (1 - compressed_length / original_length) * 100
        
        print(f"\n📊 压缩效果:")
        print(f"  - 原始长度: {original_length} 字符")
        print(f"  - 压缩后长度: {compressed_length} 字符")
        print(f"  - 压缩率: {compression_ratio:.1f}%")
        
        print(f"\n📄 压缩摘要:")
        print("=" * 60)
        print(summary)
        print("=" * 60)
        
        print(f"\n🎉 压缩演示完成！")
    else:
        print(f"  - 错误信息: {result['summary']}")


if __name__ == "__main__":
    asyncio.run(main())
