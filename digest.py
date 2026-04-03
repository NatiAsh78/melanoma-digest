import requests
from datetime import datetime, timedelta
import os
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
import xml.etree.ElementTree as ET

# === CONFIG ===
EMAIL = "asher.nati@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
"""

search = requests.get(
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    params={"db": "pubmed", "term": query, "retmax": 50, "retmode": "json"}
)
ids = search.json()["esearchresult"]["idlist"]

if not ids:
    summary = "No new melanoma publications were identified this week."
else:
    # === FETCH SUMMARY DETAILS ===
    summary_resp = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    )
    summary_data = summary_resp.json()["result"]

    # === FETCH ABSTRACTS ===
    fetch_resp = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
    )

    root = ET.fromstring(fetch_resp.text)

    abstract_map = {}

    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        if pmid_elem is None:
            continue
        pmid = pmid_elem.text

        abstract_texts = []
        for abstract in article.findall(".//Abstract/AbstractText"):
            label = abstract.attrib.get("Label")
            text = "".join(abstract.itertext()).strip()
            if text:
                if label:
                    abstract_texts.append(f"{label}: {text}")
                else:
                    abstract_texts.append(text)

        abstract_map[pmid] = " ".join(abstract_texts)

    articles = []

    for pmid in ids:
        item = summary_data.get(pmid, {})
        articles.append({
            "title": item.get("title", ""),
            "journal": item.get("fulljournalname", ""),
            "date": item.get("pubdate", ""),
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "abstract": abstract_map.get(pmid, "")
        })

    # Keep payload manageable
    articles_for_ai = articles[:30]

    prompt = f"""
You are a melanoma oncology expert preparing a weekly literature digest for a medical oncologist.

From the following articles:
1. Select the 10 most clinically important papers
2. Prioritize: randomized trials, prospective studies, guidelines, systematic reviews, meta-analyses, real-world evidence
3. Exclude basic science and lab studies

For each selected paper, summarize the ABSTRACT in a clinically useful way.

Important rules:
- Focus on actual study results, not generic background
- Extract concrete details whenever available
- Prefer numerical results from the abstract, including:
  - number of patients
  - study design
  - disease setting
  - intervention and comparator
  - primary endpoint
  - ORR / CR / DCR
  - median PFS / OS
  - hazard ratio (HR)
  - confidence interval (CI)
  - p value
- If a specific number is not available, do not invent it
- Do not use vague phrases like "improved outcomes" if actual numbers are available
- Write in clear, professional English
- Be concise but data-rich

For each paper provide exactly in this format:

1) Title
Journal + date
PubMed link: [use the exact link provided]
Study type: ...
Population: ...
Clinical question: ...
Key results: ...
Limitations: ...
Why it matters: ...

Articles:
{articles_for_ai}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    summary = response.choices[0].message.content

# === FORMAT HTML EMAIL ===
html_content = "<h2 style='font-family:Arial;'>Weekly Melanoma Literature Digest</h2>"

lines = summary.split("\n")

for line in lines:
    line = line.strip()
    if not line:
        continue

    if line.startswith(tuple(f"{i})" for i in range(1, 11))):
        html_content += f"<h3 style='font-family:Arial; color:#1a1a1a; font-size:22px; margin-top:24px;'>{line}</h3>"
    elif line.startswith("http") or line.startswith("PubMed link:"):
        url = line.replace("PubMed link:", "").strip()
        html_content += f"<p style='font-family:Arial; font-size:14px; margin:6px 0;'><a href='{url}' target='_blank'>PubMed link</a></p>"
    else:
        html_content += f"<p style='font-family:Arial; font-size:14px; line-height:1.5; margin:8px 0;'>{line}</p>"

msg = MIMEText(html_content, "html")
msg["Subject"] = "Weekly Melanoma Literature Digest"
msg["From"] = EMAIL
msg["To"] = EMAIL

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)

print("Email sent!")
