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
    # 替换镜像服务
    mirror = "https://api.allorigins.win/raw?url=" + url
    print(f"使用镜像抓取：{mirror}")
    
    try:
        resp = session.get(mirror, headers=headers, timeout=(6, 30))
        resp.raise_for_status()
        return resp.text, None
    except requests.RequestException as e:
        return None, f"镜像抓取失败：{e}"

def parse_articles_from_text(text: str, base_url: str):
    """从纯文本中解析文章"""
    articles = []
    
    # 使用正则表达式匹配文章链接模式
    # 匹配类似 "现代工科职业对女性不友好吗？女生适不适合做硬件呢？" 这样的标题
    # 后面跟着链接格式 "https://www.eet-china.com/mp/a429190.html"
    
    # 方法1：匹配标题和链接的组合
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
    
    # 方法2：如果上面没找到，尝试匹配纯文本中的文章标题
    if not articles:
        # 查找包含 "https://www.eet-china.com/mp/a" 的行
        lines = text.split('\n')
        for line in lines:
            if 'https://www.eet-china.com/mp/a' in line:
                # 提取链接
                link_match = re.search(r'https://www\.eet-china\.com/mp/a\d+\.html', line)
                if link_match:
                    link = link_match.group(0)
                    # 提取标题（链接前的文本）
                    title = line.split(link)[0].strip()
                    if title and len(title) > 5:  # 标题长度大于5
                        articles.append({
                            "title": title,
                            "link": link,
                            "summary": "",
                            "pub_date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
                        })
    
    # 方法3：更宽松的匹配，查找所有可能的文章标题
    if not articles:
        # 查找包含 "原创" 或 "浏览" 的行，这些通常是文章条目
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if ('原创' in line or '浏览' in line) and len(line.strip()) > 10:
                # 向上查找标题
                for j in range(max(0, i-3), i):
                    prev_line = lines[j].strip()
                    if prev_line and len(prev_line) > 10 and not prev_line.startswith('http'):
                        # 检查是否包含链接
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

    # 调试：输出页面结构信息
    print(f"页面标题: {soup.title.string if soup.title else '无标题'}")
    print(f"所有链接数量: {len(soup.find_all('a'))}")
    
    # 如果HTML中没有链接，尝试从纯文本解析
    if len(soup.find_all('a')) == 0:
        print("HTML中没有链接，尝试从纯文本解析...")
        return parse_articles_from_text(html, base_url)
    
    # 输出前10个链接用于调试
    print("前10个链接:")
    for i, a in enumerate(soup.find_all('a')[:10]):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        print(f"  {i+1}. {text[:50]} -> {href}")

    # 规则1：原站结构
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

    # 规则2：列表类容器通配
    if not articles:
        print("尝试列表类容器通配...")
        for container_sel in ["div[class*=list]", "section[class*=list]", "div[class*=recommend]", "section[class*=recommend]"]:
            containers = soup.select(container_sel)
            print(f"选择器 {container_sel} 找到 {len(containers)} 个容器")
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

    # 规则3：全页兜底，根据链接正则筛
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
            # 放宽条件：只要看起来像文章链接
            if (re.search(r"/(mp|article|news|a\d+)/", href, flags=re.IGNORECASE) or 
                re.search(r"\.html?$", href, flags=re.IGNORECASE) or
                len(text) > 10):  # 标题长度大于10的链接
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
        return

    if html:
        print(f"[2/4] 页面长度：{len(html)} 字符，开始解析…")
        articles = parse_articles(html, url)
    else:
        articles = []

    print(f"[3/4] 提取文章条数：{len(articles)}")
    if not articles:
        print("没有解析到任何文章。")
        return

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
