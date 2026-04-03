import requests
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText

# === CONFIG ===
EMAIL = "asher.nati@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# === DATE RANGE ===
today = datetime.today()
last_week = today - timedelta(days=7)
date_query = f"{last_week.strftime('%Y/%m/%d')}:{today.strftime('%Y/%m/%d')}"

# === PUBMED SEARCH ===
query = f"""
(melanoma[Title] OR melanoma[MeSH Terms] OR uveal melanoma[Title] OR mucosal melanoma[Title])
AND ({date_query}[Date - Publication])
AND (english[Language])
AND (humans[MeSH Terms])
NOT (animals[MeSH Terms] NOT humans[MeSH Terms])
"""

search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
params = {
    "db": "pubmed",
    "term": query,
    "retmax": 50,
    "retmode": "json"
}

response = requests.get(search_url, params=params)
ids = response.json()["esearchresult"]["idlist"]

# === FETCH DETAILS ===
fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
params = {
    "db": "pubmed",
    "id": ",".join(ids),
    "retmode": "json"
}

response = requests.get(fetch_url, params=params)
data = response.json()["result"]

# === BUILD EMAIL ===
articles = []

for pmid in ids[:20]:
    item = data[pmid]
    title = item.get("title", "")
    journal = item.get("fulljournalname", "")
    date = item.get("pubdate", "")
    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    articles.append(f"""
    <p>
    <b>{title}</b><br>
    {journal} | {date}<br>
    <a href="{link}">View on PubMed</a>
    </p>
    """)

html = f"""
<h2>Weekly Melanoma Literature Digest</h2>
{''.join(articles)}
"""

# === SEND EMAIL ===
msg = MIMEText(html, "html")
msg["Subject"] = "Weekly Melanoma Literature Digest"
msg["From"] = EMAIL
msg["To"] = EMAIL

with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    server.starttls()
    server.login(EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)

print("Email sent!")
