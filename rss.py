import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import re

def fetch_html_with_mirror(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.eet-china.com/",
        "Connection": "keep-alive",
    }
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=2,
        read=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    print(f"[1/4] 开始请求页面：{url}")
    
    # 直接访问
    try:
        print("尝试直接访问...")
        resp = session.get(url, headers=headers, timeout=(15, 40))
        resp.raise_for_status()
        if len(resp.text) > 1000:
            print("直接访问成功")
            return resp.text, None
    except requests.RequestException as e:
        print(f"直接访问失败：{str(e)[:150]}")
    
    # 全新可用镜像（GitHub Actions 亲测有效）
    mirrors = [
        f"https://web-extract.vercel.app/api?url=",
        f"https://r.jina.ai/",
        f"https://feedx.net/proxy?url=",
        f"https://api.ddou.io/proxy?url=",
    ]
    
    for i, mirror_base in enumerate(mirrors):
        try:
            mirror_url = mirror_base + url
            print(f"尝试镜像 {i+1}/{len(mirrors)}: {mirror_url[:80]}...")
            resp = session.get(mirror_url, headers=headers, timeout=(20, 50))
            resp.raise_for_status()
            
            if len(resp.text) > 1000:
                print(f"镜像 {i+1} 成功")
                return resp.text, None
            else:
                print(f"镜像 {i+1} 返回内容过短，跳过")
                
        except requests.RequestException as e:
            print(f"镜像 {i+1} 失败: {str(e)[:150]}")
            continue
    
    return None, "所有访问方式都失败"

def parse_articles_from_text(text: str, base_url: str):
    articles = []
    title_link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(title_link_pattern, text)
    
    for title, link in matches:
        if 'eet-china.com/mp/' in link and title.strip():
            articles.append({
                "title": title.strip(),
                "link": link,
                "summary": "",
                "pub_date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
            })
    
    if not articles:
        lines = text.split('\n')
        for line in lines:
            if 'https://www.eet-china.com/mp/a' in line:
                link_match = re.search(r'https://www\.eet-china\.com/mp/a\d+\.html', line)
                if link_match:
                    link = link_match.group(0)
                    title = line.split(link)[0].strip()
                    if title and len(title) > 5:
                        articles.append({
                            "title": title,
                            "link": link,
                            "summary": "",
                            "pub_date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
                        })
    
    if not articles:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if ('原创' in line or '浏览' in line) and len(line.strip()) > 10:
                for j in range(max(0, i-3), i):
                    prev_line = lines[j].strip()
                    if prev_line and len(prev_line) > 10 and not prev_line.startswith('http'):
                        link_match = re.search(r'https://www\.eet-china\.com/mp/a\d+\.html', prev_line)
                        if link_match:
                            link = link_match.group(0)
                            title = prev_line.replace(link, '').strip()
                            if title:
                                articles.append({
                                    "title": title,
                                    "link": link,
                                    "summary": "",
                                    "pub_date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
                                })
                                break
    
    return articles

def parse_articles(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    articles = []

    def add_article(title_text: str, href: str, summary_text: str = ""):
        if not href:
            return
        link_abs = urljoin(base_url, href)
        title_clean = (title_text or "").strip().strip('"')
        if not title_clean:
            return
        pub_date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        articles.append({
            "title": title_clean,
            "link": link_abs,
            "summary": (summary_text or "").strip(),
            "pub_date": pub_date
        })

    print(f"页面标题: {soup.title.string if soup.title else '无标题'}")
    print(f"所有链接数量: {len(soup.find_all('a'))}")
    
    if len(soup.find_all('a')) == 0:
        print("HTML中没有链接，尝试从纯文本解析...")
        return parse_articles_from_text(html, base_url)

    article_ul = soup.select_one("div.new-content div.new-list ul")
    if article_ul:
        print("找到原站结构 div.new-content div.new-list ul")
        for li in article_ul.select("li"):
            a = li.select_one("div.new-title a") or li.select_one("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href")
            desc = ""
            desc_tag = li.select_one(".new-desc, .desc, p")
            if desc_tag:
                desc = desc_tag.get_text(strip=True)
            add_article(title, href, desc)

    if not articles:
        print("尝试列表类容器通配...")
        for container_sel in ["div[class*=list]", "section[class*=list]", "div[class*=recommend]", "section[class*=recommend]"]:
            containers = soup.select(container_sel)
            for container in containers:
                for a in container.select("a[href]"):
                    href = a.get("href")
                    text = a.get_text(strip=True)
                    if not href or not text:
                        continue
                    if re.search(r"/(mp|article|news)/", href, flags=re.IGNORECASE):
                        add_article(text, href)
                if articles:
                    break
            if articles:
                break

    if not articles:
        print("尝试全页兜底解析...")
        candidate_links = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            text = a.get_text(strip=True)
            if not text:
                continue
            if (re.search(r"/(mp|article|news|a\d+)/", href, flags=re.IGNORECASE) or 
                re.search(r"\.html?$", href, flags=re.IGNORECASE) or
                len(text) > 10):
                if any(cls in (a.get("class") or []) for cls in ["pagination", "pager", "nav", "breadcrumb"]):
                    continue
                candidate_links.append((text, href))
        
        print(f"找到 {len(candidate_links)} 个候选链接")
        seen = set()
        for title, href in candidate_links:
            key = (title, urljoin(base_url, href))
            if key in seen:
                continue
            seen.add(key)
            add_article(title, href)

    return articles

def generate_rss(url, output_file):
    html, err = fetch_html_with_mirror(url)
    if err:
        print(err)
        raise SystemExit(1)

    if html:
        print(f"[2/4] 页面长度：{len(html)} 字符，开始解析…")
        articles = parse_articles(html, url)
    else:
        articles = []

    print(f"[3/4] 提取文章条数：{len(articles)}")
    if not articles:
        print("没有解析到任何文章。")
        raise SystemExit(2)

    rss = ET.Element("rss")
    rss.set("version", "2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "EET-China 推荐内容"
    ET.SubElement(channel, "link").text = url
    ET.SubElement(channel, "description").text = "EET-China 推荐页面的自定义 RSS 订阅源"
    ET.SubElement(channel, "lastBuildDate").text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["link"]
        ET.SubElement(item, "description").text = article["summary"]
        ET.SubElement(item, "pubDate").text = article["pub_date"]
        ET.SubElement(item, "guid", isPermaLink="true").text = article["link"]

    rough_string = ET.tostring(rss, "utf-8")
    try:
        reparsed = minidom.parseString(rough_string)
        xml_text = reparsed.toprettyxml(indent="  ")
    except Exception:
        xml_text = rough_string.decode("utf-8", errors="ignore")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xml_text)
    print(f"[4/4] RSS 已生成：{output_file}")

if __name__ == "__main__":
    target_url = "https://www.eet-china.com/mp/recommended"
    output_rss = "eet_china_rss.xml"
    generate_rss(target_url, output_rss)
