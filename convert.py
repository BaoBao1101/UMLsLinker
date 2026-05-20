"""Script đóng gói văn bản thô từ PUBMED TEXT thành file JSON chuẩn input cho O-SRE"""
import os
import json
import re
import glob

def clean_text(text: str) -> str:
    """Làm phẳng text, xóa khoảng trắng thừa và ký tự đặc biệt làm gãy JSON"""
    if not text: return ""
    # Thay thế mọi dấu xuống dòng thành dấu cách
    text = text.replace('\n', ' ').replace('\r', ' ')
    # Xóa các khoảng trắng thừa
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def prepare_json_inputs(input_dir: str = "PUBMED TEXT", output_dir: str = "OSRE_INPUTS"):
    # 1. Kiểm tra thư mục đầu vào và tạo thư mục đầu ra
    if not os.path.exists(input_dir):
        print(f"❌ Lỗi: Không tìm thấy thư mục {input_dir}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Các file JSON chuẩn sẽ được lưu tại: ./{output_dir}/")
    
    # 2. Tìm tất cả các file .txt trong thư mục PUBMED TEXT
    txt_files = glob.glob(os.path.join(input_dir, "*.txt"))
    
    if not txt_files:
        print(f"⚠️ Thư mục {input_dir} đang trống!")
        return
        
    print(f"🔍 Tìm thấy {len(txt_files)} file bệnh án. Bắt đầu đóng gói...")
    
    success_count = 0
    
    # 3. Xử lý từng file
    for filepath in txt_files:
        # Lấy tên file gốc (VD: PMID(12345).txt -> PMID(12345))
        basename = os.path.basename(filepath)
        filename_without_ext = os.path.splitext(basename)[0]
        
        # Đọc nội dung thô
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
        # Làm sạch và ép phẳng text
        cleaned_text = clean_text(raw_text)
        
        # Nếu file không có nội dung thì bỏ qua
        if not cleaned_text:
            continue
            
        # ĐÓNG GÓI VÀO CẤU TRÚC JSON CHUẨN
        payload = {
            "text": cleaned_text,
            "top_k": 3
        }
        
        # Đường dẫn file JSON đầu ra
        output_filepath = os.path.join(output_dir, f"{filename_without_ext}_input.json")
        
        # Ghi ra file JSON
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            
        success_count += 1
        
    print(f"🎉 HOÀN THÀNH! Đã đóng gói thành công {success_count} file JSON.")
    print("💡 Giờ cậu có thể ném thẳng các file này vào Swagger UI hoặc code chạy Batch!")

if __name__ == "__main__":
    prepare_json_inputs(input_dir="PUBMED TEXT", output_dir="OSRE_INPUTS")