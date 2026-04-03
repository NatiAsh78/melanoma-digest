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

html_content = """
<h2 style='font-family:Arial; color:#111;'>Weekly Melanoma Literature Digest</h2>
<p style='font-family:Arial; font-size:14px; color:#444;'>
Top clinically relevant melanoma publications from the past week
</p>
<hr>
"""

lines = summary.split("\n")

for line in lines:
    line = line.strip()
    if not line:
        continue

    # Title (numbered)
    if line.startswith(tuple(f"{i})" for i in range(1, 11))):
        html_content += f"""
        <div style='margin-top:28px'>
        <div style='font-family:Arial; font-size:20px; font-weight:bold; color:#000;'>
        {line}
        </div>
        """

    # Journal line
    elif "Journal + date:" in line:
        html_content += f"""
        <div style='font-family:Arial; font-size:13px; color:#666; margin-top:4px'>
        {line.replace("Journal + date:", "")}
        </div>
        """

    # PubMed link
    elif "http" in line:
        url = line.split("http")[-1]
        url = "http" + url
        html_content += f"""
        <div style='margin:6px 0 12px 0'>
        <a href="{url}" style='font-family:Arial; font-size:13px; color:#1a73e8;' target='_blank'>
        View on PubMed
        </a>
        </div>
        """

    # Key results → highlight
    elif "Key results:" in line:
        html_content += f"""
        <div style='font-family:Arial; font-size:14px; margin-top:10px'>
        <b>Key results:</b> <span style='color:#000'>{line.replace("Key results:", "")}</span>
        </div>
        """

    # Why it matters → subtle emphasis
    elif "Why it matters:" in line:
        html_content += f"""
        <div style='font-family:Arial; font-size:14px; margin-top:6px; color:#333'>
        <b>Why it matters:</b> {line.replace("Why it matters:", "")}
        </div>
        <hr style='margin-top:20px'>
        """

    # Other fields
    else:
        clean = line.replace("**", "").replace("Title:", "").replace("Study type:", "<b>Study type:</b>") \
                    .replace("Population:", "<b>Population:</b>") \
                    .replace("Clinical question:", "<b>Clinical question:</b>") \
                    .replace("Limitations:", "<b>Limitations:</b>")

        html_content += f"""
        <div style='font-family:Arial; font-size:14px; margin-top:6px; color:#333'>
        {clean}
        </div>
        """

msg = MIMEText(html_content, "html")
msg["Subject"] = "Weekly Melanoma Literature Digest"
msg["From"] = EMAIL
msg["To"] = EMAIL

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(EMAIL, EMAIL_PASSWORD)
    server.send_message(msg)

print("Email sent!")
