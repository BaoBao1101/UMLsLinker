"""FastAPI Server cho O-SRE NLP Engine."""
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import Lõi Engine của bạn
from src.linker.engine import OpenUMLSEngine

# Cấu hình log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Khởi tạo App và Engine (Engine sẽ được load vào RAM ngay khi chạy server)
app = FastAPI(title="O-SRE Medical NLP API", version="1.0")

logger.info("Đang khởi động OpenUMLSEngine... (Sẽ mất vài giây để nạp Vectors)")
try:
    engine = OpenUMLSEngine()
    logger.info("Khởi động Engine THÀNH CÔNG!")
except Exception as e:
    logger.error("Lỗi khi khởi động Engine: %s", e)
    engine = None

# Định nghĩa cấu trúc cục data client gửi lên
class ClinicalRequest(BaseModel):
    text: str
    top_k: int = 5

@app.get("/")
def health_check():
    return {"status": "ok", "message": "O-SRE Engine is running. Gửi POST tới /extract"}

@app.post("/extract")
def extract_clinical_entities(payload: ClinicalRequest):
    if not engine:
        raise HTTPException(status_code=500, detail="Engine chưa sẵn sàng.")
    
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text không được để trống.")
        
    try:
        # Gọi Engine xử lý bệnh án
        results = engine.map_document(payload.text, top_k=payload.top_k)
        return {
            "status": "success",
            "data": results
        }
    except Exception as e:
        logger.error("Lỗi trích xuất: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Lệnh chạy server cục bộ trên port 8000
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)