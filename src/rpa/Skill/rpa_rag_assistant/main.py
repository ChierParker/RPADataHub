"""
RPA RAG 知识库引擎 — 私有文档检索 + DeepSeek 生成回答
"""

import os, re, json, sqlite3
from pathlib import Path

# 知识库目录
KB_DIR = Path(__file__).resolve().parent / "knowledge_base"
DB_PATH = KB_DIR / "rag_index.db"


class RAGEngine:
    """轻量级 RAG 引擎: SQLite FTS5 全文检索 + DeepSeek 生成"""

    def __init__(self, ai_call=None):
        self.ai_call = ai_call or (lambda p: "AI未配置")
        self._init_db()
        self._load_documents()

    # ============================================================
    # 数据库初始化
    # ============================================================

    def _init_db(self):
        """初始化 FTS5 全文索引表"""
        self._conn = sqlite3.connect(str(DB_PATH))
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                title, source, content, tokenize='unicode61'
            )
        """)
        self._conn.commit()

    # ============================================================
    # 文档加载与分块
    # ============================================================

    def _load_documents(self):
        """加载 knowledge_base/ 下所有 .md/.txt 文档并入库"""
        # 检查是否已索引
        row = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        if row[0] > 0:
            return  # 已索引, 跳过

        docs = []
        for f in sorted(KB_DIR.glob("*.md")) + sorted(KB_DIR.glob("*.txt")):
            source = f.name
            title = source.replace(".md", "").replace(".txt", "").replace("_", " ").title()
            content = f.read_text(encoding="utf-8")
            # 分块: 500 字一块, 重叠 100 字
            chunks = self._chunk_text(content, 500, 100)
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) > 50:
                    docs.append((f"{title} #{i+1}", source, chunk.strip()))

        # 批量插入
        if docs:
            self._conn.executemany(
                "INSERT INTO chunks (title, source, content) VALUES (?, ?, ?)", docs
            )
            self._conn.commit()
            print(f"[RAG] 索引完成: {len(docs)} chunks from {len(set(d[1] for d in docs))} docs")
        else:
            print("[RAG] 无文档可索引, 请补充 knowledge_base/ 下的 .md 文件")

    @staticmethod
    def _chunk_text(text, chunk_size=500, overlap=100):
        """文本分块"""
        # 按段落分割
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) < chunk_size:
                current += para + "\n"
            else:
                if current:
                    chunks.append(current)
                current = para[-overlap:] + "\n" + para if len(current) > overlap else para + "\n"
        if current:
            chunks.append(current)
        return chunks or [text]

    # ============================================================
    # 检索 + 生成
    # ============================================================

    def ask(self, question):
        """RAG 问答入口"""
        # 1. 检索相关文档
        chunks = self._retrieve(question, top_k=5)

        # 2. 构建 Prompt
        if chunks:
            context = "\n\n---\n\n".join(
                f"[{c[0]}] {c[2]}" for c in chunks
            )
            prompt = f"""你是 RPA 数据采集运维平台的 AI 技术专家。请根据以下知识库内容回答用户问题。

知识库内容:
{context}

用户问题: {question}

要求: 用中文回答，引用知识库中的具体内容。如果知识库中没有相关信息，请诚实告知。
回答:"""
        else:
            prompt = f"""你是 RPA 数据采集运维平台的 AI 技术专家。
用户问题: {question}
知识库中暂无相关文档，请根据你的通用知识回答。
回答:"""

        # 3. AI 生成
        answer = self.ai_call(prompt)
        sources = list(set(c[0] for c in chunks)) if chunks else []

        return {
            "answer": answer or "知识库检索失败",
            "sources": sources,
            "chunk_count": len(chunks),
        }

    def _retrieve(self, question, top_k=5):
        """FTS5 全文检索"""
        # 提取关键词
        keywords = " OR ".join(
            w for w in re.findall(r'[一-鿿]+|[a-zA-Z]+', question)
            if len(w) >= 2
        )
        if not keywords:
            keywords = question.replace(" ", " OR ")

        try:
            rows = self._conn.execute(
                "SELECT title, source, content, rank FROM chunks WHERE chunks MATCH ? "
                "ORDER BY rank LIMIT ?",
                (keywords, top_k)
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 语法错误时降级为 LIKE 查询
            rows = []
            for word in keywords.split(" OR ")[:5]:
                word = word.strip().strip('"').strip("'")
                if len(word) >= 2:
                    r = self._conn.execute(
                        "SELECT title, source, content, 1 as rank FROM chunks "
                        "WHERE content LIKE ? LIMIT 2",
                        (f"%{word}%",)
                    ).fetchall()
                    rows.extend(r)
            rows = rows[:top_k]

        return rows

    def rebuild(self):
        """重建索引"""
        self._conn.execute("DELETE FROM chunks")
        self._conn.commit()
        self._load_documents()

    def get_stats(self):
        """知识库统计"""
        row = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        sources = self._conn.execute(
            "SELECT DISTINCT source FROM chunks"
        ).fetchall()
        return {
            "total_chunks": row[0],
            "documents": len(sources),
            "sources": [s[0] for s in sources],
        }


# ============================================================
# 便捷函数
# ============================================================

def create_rag_engine(ai_call=None):
    """创建 RAG 引擎实例"""
    return RAGEngine(ai_call)


def ask_rag(question, api_key=None):
    """一键 RAG 问答 (用于测试)"""
    import requests

    def _ai(prompt):
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 800, "temperature": 0.3},
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return ""

    engine = RAGEngine(_ai)
    return engine.ask(question)
