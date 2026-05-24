from pydantic import BaseModel


class Comment(BaseModel):
    author: str
    content: str
    likes: int = 0


class Post(BaseModel):
    id: str
    title: str
    content: str
    likes: int = 0
    author: str = ""
    created_at: str = ""
    comments: list[Comment] = []
    url: str = ""
    tags: list[str] = []
