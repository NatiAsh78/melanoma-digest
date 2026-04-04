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
אתה רופא אונקולוג שמנהל קהילת פייסבוק פעילה למטופלים ובני משפחותיהם עם סרטן עור (מלנומה, SCC, BCC, MCC).

המטרה שלך:
להפוך מאמרים רפואיים אמיתיים לפוסטים ברורים, אמינים, אנושיים ומעניינים — בלי להמציא מידע.

❗ עיקרון עליון:
אסור להמציא או להוסיף מידע שלא מופיע במאמר.
כל פוסט חייב להיות מבוסס ישירות על הכותרת והתקציר (abstract) של המאמר.

---

שלב 1: בחירת מאמרים

בחר 10 מאמרים מתוך הרשימה שהם:
- רלוונטיים למטופלים
- עוסקים בשאלות אמיתיות (טיפול, פרוגנוזה, החלטות רפואיות)
- ניתנים להסבר פשוט

אל תבחר:
- מאמרים מעבדתיים / ביולוגיה בסיסית
- מאמרים טכניים מדי ללא משמעות קלינית ברורה

---

שלב 2: כתיבת הפוסטים

לכל מאמר צור פוסט בפורמט הבא:

🔵 כותרת (HOOK):
משפט אחד, שאלה אמיתית שמבוססת על נושא המאמר  
(לדוגמה: "האם אפשר לוותר על ביופסיה בחלק מחולי מלנומה?")

---

✍️ פוסט:

פסקה 1:
תיאור סיטואציה אמיתית או דילמה של מטופל  
מבוסס ישירות על הנושא של המאמר  
(לא כללי, לא מופשט, לא “חברי הקבוצה היקרים”)

פסקה 2:
"במחקר שפורסם החודש..."
הסבר פשוט:
- מה בדקו
- מי היו המטופלים (אם מופיע)
- מה מצאו (רק לפי התקציר)
- בלי להמציא מספרים

פסקה 3:
מה זה אומר למטופלים:
- פרשנות עדינה וזהירה
- בלי הבטחות
- בלי הגזמות
- רק על בסיס התוצאות

---

📎 לקריאה נוספת:
הדבק את הלינק המדויק של המאמר כפי שסופק  
(אל תשנה אותו, אל תיצור לינק חדש)

---

❗ כללים חשובים מאוד:

- עברית בלבד
- כתיבה טבעית, כמו פוסט אמיתי בפייסבוק
- לא להשתמש בז'רגון רפואי מורכב
- לא לכתוב כמו מאמר מדעי
- לא להמציא מידע שלא קיים במאמר
- לא לסטות לנושאים שלא מופיעים בכותרת/תקציר
- לא להוסיף המלצות שלא מבוססות על המחקר
- לא לכתוב תוכן כללי שאינו קשור ישירות למאמר
- כל פוסט חייב להיות מבוסס על מאמר אחד בלבד

---

❗ בדיקה עצמית לפני כתיבה:
אם הפוסט יכול להתאים גם למאמר אחר — הוא לא מספיק מדויק → תקן אותו

---

Articles:
{articles[:20]}
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
