import requests
from datetime import datetime, timedelta
import os
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMAIL = "asher.nati@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# === DATE RANGE ===
today = datetime.today()
last_week = today - timedelta(days=7)
date_query = f"{last_week.strftime('%Y/%m/%d')}:{today.strftime('%Y/%m/%d')}"

# === SEARCH PUBMED ===
query = f"""
(melanoma[Title] OR melanoma[MeSH Terms] OR uveal melanoma[Title] OR mucosal melanoma[Title])
AND ({date_query}[Date - Publication])
AND (english[Language])
AND (humans[MeSH Terms])
"""

search = requests.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    params={"db": "pubmed", "term": query, "retmax": 50, "retmode": "json"}
)

ids = search.json()["esearchresult"]["idlist"]

# === FETCH DETAILS ===
fetch = requests.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
    params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
)

data = fetch.json()["result"]

articles = []

for pmid in ids:
    item = data[pmid]
    title = item.get("title", "")
    journal = item.get("fulljournalname", "")
    date = item.get("pubdate", "")
    link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    articles.append({
        "title": title,
        "journal": journal,
        "date": date,
        "link": link
    })

# === AI FILTER + RANK ===
prompt = f"""
You are a melanoma oncology expert.

From the following list of articles:
1. Select the 10 most clinically important papers
2. Prioritize: RCTs, prospective studies, guidelines, reviews, real-world evidence
3. Exclude basic science and lab studies
4. For each selected paper provide:
- Title
- Short clinical summary (4-5 lines)
- Why it matters

Articles:
{articles}
"""

response = client.chat.completions.create(
    model="gpt-5",
    messages=[{"role": "user", "content": prompt}],
)

summary = response.choices[0].message.content

# === EMAIL ===
msg = MIMEText(summary, "plain")
msg["Subject"] = "Weekly Melanoma Literature Digest"
msg["From"] = EMAIL
msg["To"] = EMAIL

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)

print("Sent!")
