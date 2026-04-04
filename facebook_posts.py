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
# === AI: GENERATE FACEBOOK POST PER ARTICLE ===

def generate_post(article):
    prompt = f"""
אתה רופא אונקולוג שמנהל קהילת פייסבוק למטופלים ובני משפחותיהם עם סרטן עור.

המטרה שלך:
לכתוב פוסט אמיתי לפייסבוק על בסיס מאמר אחד בלבד.

❗ כללים קריטיים:
- אסור להמציא מידע
- אסור לסטות מהמאמר
- כל מה שאתה כותב חייב להתבסס על הכותרת והתקציר בלבד
- אם מידע לא מופיע — אל תכתוב אותו

---

Title:
{article['title']}

Abstract:
{article['abstract']}

Link:
{article['link']}

---

כתוב פוסט בפורמט הבא:

🔵 כותרת:
משפט אחד ברור, אנושי, מושך — שמבוסס ישירות על נושא המאמר  
(לא כללי, לא מופשט)

---

✍️ פוסט:

פסקה 1:
תאר סיטואציה אמיתית מהחיים או שאלה שמטופלים שואלים  
(חייב להיות קשור ישירות לנושא המאמר)

פסקה 2:
"במחקר שפורסם החודש..."
הסבר פשוט:
- מה בדקו
- מי היו המטופלים (אם מופיע)
- מה מצאו (רק לפי התקציר)
- בלי מספרים אם לא בטוחים

פסקה 3:
מה המשמעות למטופלים:
- פרשנות עדינה בלבד
- בלי הגזמות
- בלי הבטחות

---

📎 לקריאה נוספת:
{article['link']}

---

כללים נוספים:
- עברית בלבד
- עברית טבעית (לא תרגום מכונה)
- לא להשתמש בז'רגון רפואי מורכב
- לא לכתוב כמו מאמר מדעי
- לא רשימות
- לא “פסקה 1/2/3”
- לא משפטים לא ברורים

אם הפוסט לא ברור — קצר אותו וכתוב בצורה פשוטה יותר.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content


# === RUN ON TOP 10 ARTICLES ===

selected_articles = articles[:10]

posts = []

for article in selected_articles:
    post = generate_post(article)
    posts.append(post)


# === COMBINE POSTS ===

content = "\n\n=========================\n\n".join(posts)

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
