"""Script hút PubMed Công nghiệp: Search -> Map -> Chia lô Batch Processing -> Bóc tách Case Report"""
import requests
import xml.etree.ElementTree as ET
import re
import os

def clean_text(text: str) -> str:
    if not text: return ""
    text = text.replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def chunk_list(lst: list, chunk_size: int):
    """Hàm cắt danh sách dài thành các lô (batch) nhỏ"""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def fetch_pubmed_to_pmc_cases(pubmed_query: str, max_results: int = 500, output_dir: str = "PUBMED TEXT"):
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"📁 Dữ liệu sẽ được lưu tại thư mục: ./{output_dir}/")

        # BƯỚC 1: TÌM KIẾM TRÊN KHO PUBMED
        print(f"🔍 BƯỚC 1: Tìm kiếm tối đa {max_results} bài báo trên PubMed...")
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        search_data = {
            "db": "pubmed",
            "term": pubmed_query,
            "retmax": max_results,
            "retmode": "json"
        }
        
        # Dùng POST thay vì GET để tránh giới hạn độ dài URL
        search_res = requests.post(search_url, data=search_data)
        search_res.raise_for_status()
        pmids = search_res.json().get("esearchresult", {}).get("idlist", [])
        
        if not pmids:
            print("❌ Không tìm thấy PMID nào hợp lệ từ PubMed.")
            return
            
        print(f"✅ Tìm thấy {len(pmids)} bài PubMed. Bắt đầu chia lô để xử lý (Batch Processing)...")
        
        success_count = 0
        batches = list(chunk_list(pmids, 50)) # Chia mỗi lô 50 bài báo
        
        # XỬ LÝ TỪNG LÔ
        for batch_idx, pmid_batch in enumerate(batches, 1):
            print(f"\n⏳ Đang xử lý Lô {batch_idx}/{len(batches)} (Gồm {len(pmid_batch)} bài báo)...")
            
            # BƯỚC 2: ÁNH XẠ PMID SANG PMCID (DÙNG E-LINK + POST)
            elink_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
            elink_data = {
                "dbfrom": "pubmed",
                "db": "pmc",
                "id": ",".join(pmid_batch),
                "retmode": "json"
            }
            
            elink_res = requests.post(elink_url, data=elink_data)
            
            if elink_res.status_code != 200:
                print(f"   [-] Lỗi E-Link lô này: {elink_res.status_code}")
                continue
                
            linksets = elink_res.json().get("linksets", [])
            pmcids = []
            pmc_to_pmid = {}
            
            for linkset in linksets:
                original_pmid = linkset.get("ids", [""])[0] 
                if "linksetdbs" in linkset:
                    for linksetdb in linkset["linksetdbs"]:
                        if linksetdb["linkname"] == "pubmed_pmc":
                            for link in linksetdb["links"]:
                                pmcids.append(link)
                                pmc_to_pmid[link] = original_pmid
                            
            if not pmcids:
                print("   [-] Lô này không có bản Free Full Text nào trên PMC. Bỏ qua.")
                continue
                
            # BƯỚC 3: TẢI FULL TEXT TỪ PMC (DÙNG E-FETCH + POST)
            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            fetch_data = {
                "db": "pmc",
                "id": ",".join(pmcids),
                "retmode": "xml"
            }
            
            fetch_res = requests.post(fetch_url, data=fetch_data)
            if fetch_res.status_code != 200:
                print(f"   [-] Lỗi E-Fetch tải XML lô này: {fetch_res.status_code}")
                continue
            
            root = ET.fromstring(fetch_res.content)
            
            for article in root.findall('.//article'):
                pmid_elem = article.find('.//article-id[@pub-id-type="pmid"]')
                pmc_id_elem = article.find('.//article-id[@pub-id-type="pmc"]')
                
                pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
                if pmid == "Unknown" and pmc_id_elem is not None:
                    pmid = pmc_to_pmid.get(pmc_id_elem.text, f"PMC{pmc_id_elem.text}")
                
                case_text_parts = []
                
                for sec in article.findall('.//sec'):
                    title_elem = sec.find('title')
                    if title_elem is not None and title_elem.text:
                        title_text = title_elem.text.lower()
                        keywords = ["case presentation", "case report", "case description", "clinical presentation", "case history"]
                        if any(keyword in title_text for keyword in keywords):
                            for p in sec.findall('.//p'):
                                paragraph_text = "".join(p.itertext())
                                cleaned_p = clean_text(paragraph_text)
                                if cleaned_p:
                                    case_text_parts.append(cleaned_p)
                
                if case_text_parts:
                    full_text = " ".join(case_text_parts)
                    filename = os.path.join(output_dir, f"PMID{pmid}.txt")
                    
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(full_text)
                        
                    print(f"   [+] Đã xuất file: {filename}")
                    success_count += 1
            
        print(f"\n🎉 HOÀN THÀNH TỔNG CỘNG! Đã trích xuất thành công {success_count} bệnh án vào thư mục {output_dir}")
            
    except Exception as e:
        print(f"⚠️ Lỗi hệ thống: {e}")

if __name__ == "__main__":
    PUBMED_QUERY = """(("lumbarised"[All Fields] OR "lumbarization"[All Fields] OR "lumbarized"[All Fields] OR "lumbars"[All Fields] OR "lumbosacral region"[MeSH Terms] OR ("lumbosacral"[All Fields] AND "region"[All Fields]) OR "lumbosacral region"[All Fields] OR "lumbar"[All Fields]) AND ("spinal"[All Fields] OR "spinalization"[All Fields] OR "spinalized"[All Fields] OR "spinally"[All Fields] OR "spinals"[All Fields]) AND ("case reports"[Publication Type] OR "case report"[All Fields])) AND ((ffrft[Filter]) AND (casereports[Filter]))"""
    
    # Kéo ga 500 bài thoải mái, hệ thống sẽ tự cắt lô nhỏ!
    fetch_pubmed_to_pmc_cases(pubmed_query=PUBMED_QUERY, max_results=500, output_dir="PUBMED TEXT")