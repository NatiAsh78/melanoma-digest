import requests
from datetime import datetime, timedelta
import os
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
import xml.etree.ElementTree as ET

EMAIL = "asher.nati@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === DATE ===
today = datetime.today()
last_week = today - timedelta(days=7)
date_query = f"{last_week.strftime('%Y/%m/%d')}:{today.strftime('%Y/%m/%d')}"

# === PUBMED QUERY ===
query = f"""
(
melanoma[Title]
OR "cutaneous melanoma"[Title]
OR "uveal melanoma"[Title]
OR "mucosal melanoma"[Title]
OR "basal cell carcinoma"[Title]
OR "cutaneous squamous cell carcinoma"[Title]
OR "merkel cell carcinoma"[Title]
)
AND ({date_query}[Date - Publication])
AND (english[Language])
AND (humans[MeSH Terms])
NOT (animals[MeSH Terms] NOT humans[MeSH Terms])
"""

# === SEARCH ===
search = requests.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    params={"db": "pubmed", "term": query, "retmax": 40, "retmode": "json"}
)

ids = search.json()["esearchresult"]["idlist"]

# === FETCH ABSTRACTS ===
fetch = requests.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
    params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
)

root = ET.fromstring(fetch.text)

articles = []

for article in root.findall(".//PubmedArticle"):
    pmid = article.find(".//PMID").text

    title = article.findtext(".//ArticleTitle", default="")

    abstract_parts = []
    for a in article.findall(".//AbstractText"):
        abstract_parts.append("".join(a.itertext()))

    abstract = " ".join(abstract_parts)

    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    articles.append({
        "title": title,
        "abstract": abstract,
        "link": link
    })

# === AI PROMPT ===
prompt = f"""
אתה רופא אונקולוג שמנהל קהילת פייסבוק למטופלים ובני משפחותיהם עם סרטן עור.

המטרה שלך היא לקחת מאמרים רפואיים חדשים ולהפוך אותם לפוסטים ברורים, אנושיים ומעניינים בעברית.

בחר 10 מאמרים מתוך הרשימה שהם הכי מתאימים לפוסט לקהילה.

קריטריונים:
- נושא שמעניין מטופלים
- משהו שמשפיע על החלטות או הבנה של המחלה
- משהו שאפשר להסביר בפשטות
- הימנע ממאמרים טכניים/מעבדתיים

לכל מאמר צור פוסט בפורמט הבא:

פסקה 1:
הבעיה / שאלה אמיתית שמטופלים מתמודדים איתה

פסקה 2:
הסבר פשוט של המחקר
ציין: "במחקר שפורסם החודש"
הסבר מה בדקו ומה מצאו

פסקה 3:
מה המשמעות למטופלים

דרישות:
- עברית בלבד
- שפה פשוטה
- טון אנושי וחם
- 2–3 פסקאות
- לא להשתמש בז'רגון רפואי כבד
- לא להמציא מידע

Articles:
{articles[:30]}
"""

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
)

content = response.choices[0].message.content

# === EMAIL ===
msg = MIMEText(content, "plain", "utf-8")
msg["Subject"] = "Weekly Facebook Posts - Skin Cancer"
msg["From"] = EMAIL
msg["To"] = EMAIL

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)

print("Posts sent!")
