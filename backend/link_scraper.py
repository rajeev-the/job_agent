import re
import requests
from bs4 import BeautifulSoup

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HEADERS_BOT = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "*/*",
}


def clean_html_text(html_content: str) -> str:
    """Strip unnecessary tags, styles, scripts and return clean text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for script_or_style in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        script_or_style.extract()

    # Get text and clean multiple spaces/newlines
    lines = (line.strip() for line in soup.get_text().splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    return text


def scrape_linkedin_job(url: str) -> str:
    """Scrape a LinkedIn job posting by URL or extracted job ID."""
    job_id_match = re.search(r"view/(?:[a-zA-Z0-9_-]+-)?([0-9]+)", url) or re.search(r"currentJobId=([0-9]+)", url) or re.search(r"jobPosting:([0-9]+)", url)
    
    if job_id_match:
        job_id = job_id_match.group(1)
        api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        resp = requests.get(api_url, headers=HEADERS_BROWSER, timeout=12)
        if resp.status_code == 200 and len(resp.text) > 100:
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.find(["h2", "h1"], class_=lambda c: c and "title" in c)
            criteria = soup.find("ul", class_=lambda c: c and "criteria" in c)
            description = soup.find("div", class_=lambda c: c and ("description" in c or "markup" in c))
            
            parts = []
            if title:
                parts.append("Job Title: " + title.get_text(strip=True))
            if criteria:
                parts.append("Criteria:\n" + criteria.get_text(separator=" ", strip=True))
            if description:
                desc_text = description.get_text(separator="\n", strip=True)
                parts.append("Description:\n" + desc_text)
            
            if parts:
                return "\n\n".join(parts)
            return clean_html_text(resp.text)

    # Fallback to direct page request
    resp = requests.get(url, headers=HEADERS_BROWSER, timeout=12)
    return clean_html_text(resp.text)


def scrape_linkedin_post(url: str) -> str:
    """Scrape a LinkedIn feed update or public post."""
    # First try social bot headers which LinkedIn serves with meta tags
    resp = requests.get(url, headers=HEADERS_BOT, timeout=12)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    og_desc = soup.find("meta", property="og:description")
    og_title = soup.find("meta", property="og:title")
    
    parts = []
    if og_title and og_title.get("content"):
        parts.append(og_title["content"])
    if og_desc and og_desc.get("content"):
        parts.append(og_desc["content"])
        
    if parts:
        return "\n\n".join(parts)

    # Browser fallback
    resp_browser = requests.get(url, headers=HEADERS_BROWSER, timeout=12)
    return clean_html_text(resp_browser.text)


def scrape_instagram(url: str) -> str:
    """Scrape an Instagram post/reel caption using fast OpenGraph crawler or instaloader."""
    shortcode_match = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    shortcode = shortcode_match.group(1) if shortcode_match else None

    # Method 1: Fast OpenGraph crawler (whitelisted by Instagram for WhatsApp link previews)
    try:
        clean_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else url
        resp = requests.get(clean_url, headers=HEADERS_BOT, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_desc = soup.find("meta", property="og:description")
            og_title = soup.find("meta", property="og:title")
            content = []
            if og_title and og_title.get("content"):
                content.append(og_title["content"])
            if og_desc and og_desc.get("content"):
                desc = og_desc["content"]
                if ":" in desc:
                    desc = desc.split(":", 1)[1].strip()
                content.append(desc)
            combined = "\n\n".join(c for c in content if c).strip()
            if len(combined) > 30:
                return f"Instagram Post:\n\n{combined}"
    except Exception:
        pass

    # Method 2: Instaloader (fail-fast without 666s retry sleep)
    if shortcode:
        try:
            import instaloader
            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                max_connection_attempts=1,
                request_timeout=4,
            )
            # NEVER allow instaloader to sleep on 429
            L.context.raise_all_errors = True
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            caption = post.caption or ""
            owner = post.owner_username or ""
            if caption and len(caption) > 20:
                return f"Instagram Post by @{owner}:\n\n{caption}"
        except Exception:
            pass

    raise ValueError(
        "Instagram blocked automated access to this post (login protection). "
        "Please copy and paste the job description or caption text here on WhatsApp directly!"
    )


def scrape_generic_job_page(url: str) -> str:
    """Scrape any career page, Greenhouse, Lever, Indeed, or company job listing."""
    resp = requests.get(url, headers=HEADERS_BROWSER, timeout=12)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for common JD containers
    jd_container = soup.find(
        ["div", "section", "article", "main"],
        class_=lambda c: c and any(k in str(c).lower() for k in ["job", "description", "details", "posting", "content"]),
    )
    if jd_container:
        return clean_html_text(str(jd_container))

    return clean_html_text(resp.text)


def scrape_job_link(url: str) -> str:
    """Main dispatcher to scrape any job URL based on domain."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    lower_url = url.lower()

    if "linkedin.com/jobs" in lower_url:
        text = scrape_linkedin_job(url)
    elif "linkedin.com" in lower_url:
        text = scrape_linkedin_post(url)
    elif "instagram.com" in lower_url:
        text = scrape_instagram(url)
    else:
        text = scrape_generic_job_page(url)

    text = text.strip()
    if not text or len(text) < 30:
        raise ValueError("Could not extract readable job text from this URL. Please verify the link is public.")

    # Limit to reasonable context length for LLM (e.g. first 6,000 chars)
    if len(text) > 8000:
        text = text[:8000]

    return text
