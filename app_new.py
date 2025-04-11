from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import openai

app = Flask(__name__)
CORS(app)  

# API KEY(Naver Map(사용X), Kakao, OpenAI)
# MAPS_CLIENT_ID = "key1"
# MAPS_CLIENT_SECRET = "key2"
KAKAO_REST_API_KEY = "key3"
OPENAI_API_KEY = "key4"

openai.api_key = OPENAI_API_KEY


# 네이버 뉴스 API 설정
def fetch_news(region, category):
    API_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
    CLIENT_ID = "key5"
    CLIENT_SECRET = "key6"
    query = f"{region} {category}"
    
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }
    
    params = {
        "query": query,
        "display": 10,
        "start": 1,
        "sort": "sim",
    }
    
    response = requests.get(API_ENDPOINT, headers=headers, params=params)
    if response.status_code == 200:
        items = response.json().get("items", [])
        return [
            {
                "title": item["title"].replace("<b>", "").replace("</b>", ""),
                "link": item["link"],
                "description": item.get("description", "기사 본문의 요약문이 없습니다.").replace("<b>", "").replace("</b>", "") 
            }
            for item in items
        ]
    return []

# ChatGPT API를 사용한 지역명 추출 함수 ('지역+카테고리' 고려)
def extract_region_chatgpt(text, target_region, category):
    prompt = f"""
    다음 뉴스 기사를 분석하고 '{target_region}' + '{category}'와 가장 관련된 장소 오직 한 개만 추출해줘. 
    추출된 장소는 {target_region}내에 있어야 돼: 
    "{text}"
    결과는 쉼표로 구분된 리스트로 제공해줘.
    """

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an AI that extracts only relevant location names from news articles."},
            {"role": "user", "content": prompt}
        ]
    )
    extracted_text = response["choices"][0]["message"]["content"].strip()
    locations = [loc.strip() for loc in extracted_text.split(",") if loc.strip()]
    print(f"[ChatGPT] Extracted locations (category-aware): {locations}")
    return locations if locations else None

# 네이버 지도 API를 활용한 좌표 변환 함수
def fetch_coordinates(region_name, target_region=None):
    BASE_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
    }

    # 예: "응봉산" → "성동구 응봉산"
    query = f"{target_region} {region_name}" if target_region and target_region not in region_name else region_name
    params = {"query": query.strip()}

    response = requests.get(BASE_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        documents = data.get("documents", [])
        if documents:
            place = documents[0]  # 관련도 가장 높은 장소
            return {
                "name": place.get("place_name"),
                "lat": place.get("y"),
                "lng": place.get("x"),
                "address": place.get("address_name")
            }
        else:
            print(f"[WARN] 장소 검색 결과 없음: {query}")
            print("[DEBUG] 응답:", data)
    else:
        print(f"[ERROR] 카카오 장소 검색 실패: {query}, Status: {response.status_code}")
        print("[DEBUG] 응답 내용:", response.text)

    return None


   
# 뉴스 데이터에 좌표 추가
def enhance_news_with_coordinates(news_data, target_region, category):
    enhanced_news = []

    for article in news_data:
        region_names = extract_region_chatgpt(article["description"], target_region, category)
        print(f"[INFO] Extracted regions from news: {region_names}")

        locations = []
        if region_names:
            for region in region_names:
                coordinates = fetch_coordinates(region, target_region)
                if coordinates:
                    locations.append({
                        "name": region,
                        "lat": coordinates["lat"],
                        "lng": coordinates["lng"]
                    })
        
        article["locations"] = locations
        enhanced_news.append(article)
    
    return enhanced_news

# 뉴스 검색 API
@app.route("/search_news", methods=["GET"])    
def search_news():
    region = request.args.get("region")
    category = request.args.get("category")
    
    if not region or not category:
        return jsonify({"error": "Region and category are required"}), 400
    
    news_data = fetch_news(region, category)
    enhanced_news = enhance_news_with_coordinates(news_data, region, category)
    
    return jsonify({
        "region": region,
        "category": category,
        "news": enhanced_news,
    })

def route_search():
    origin = request.args.get("origin")
    destination = request.args.get("destination")

    if not origin or not destination:
        return jsonify({"error": "origin and destination are required"}), 400

    origin_coords = fetch_coordinates(origin)
    dest_coords = fetch_coordinates(destination)

    if not origin_coords or not dest_coords:
        return jsonify({"error": "좌표를 찾을 수 없습니다."}), 400

    url = "https://apis-navi.kakaomobility.com/v1/directions/transit"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "origin": {
            "x": origin_coords["lng"],
            "y": origin_coords["lat"]
        },
        "destination": {
            "x": dest_coords["lng"],
            "y": dest_coords["lat"]
        },
        "priority": "RECOMMEND"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        route_info = response.json()
        return jsonify(route_info)
    else:
        print("[ERROR] 카카오 경로 탐색 실패", response.text)
        return jsonify({"error": "경로 탐색 실패"}), 500

if __name__ == "__main__":
    app.run(debug=True)
