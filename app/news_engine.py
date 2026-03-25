import sqlite3
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

@dataclass
class NewsAssessment:
    symbol: str
    bias_score: int
    summary_lines: list[str]
    top_titles: list[str]
    priority: str = "INFO"
    sec_hits: list[str] | None = None

class NewsEngine:
    def __init__(self, finnhub_api_key="", newsapi_key="", sec_user_agent="", db_path="news_alerts.db"):
        self.finnhub_api_key = finnhub_api_key.strip()
        self.sec_user_agent = sec_user_agent.strip()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen_news_alpha (fingerprint TEXT PRIMARY KEY, created_at TEXT)")
        self.conn.commit()
        self.breaking = ["breaking", "just announced", "developing"]
        self.strong_pos = ["definitive agreement", "acquire", "acquisition", "purchase", "bought", "stake", "raises guidance", "beats estimates", "record backlog", "strategic partnership", "contract win", "buyback", "insider bought"]
        self.soft_pos = ["upgrade", "strong demand", "partnership", "design win", "new product", "approval"]
        self.strong_neg = ["cuts guidance", "misses estimates", "lawsuit", "investigation", "fraud", "dilution", "offering", "recall", "downgrade", "probe", "antitrust"]
        self.rumor = ["reportedly", "could", "may", "might", "rumor", "talks", "considering", "exploring", "said to be"]
        self.sec_ciks = {
            "AAPL": ("320193", "Apple Inc."),
            "MSFT": ("789019", "Microsoft Corp"),
            "NVDA": ("1045810", "NVIDIA CORP"),
            "AMD": ("2488", "ADVANCED MICRO DEVICES INC"),
            "GOOGL": ("1652044", "Alphabet Inc."),
            "AMZN": ("1018724", "Amazon.com, Inc."),
            "META": ("1326801", "Meta Platforms, Inc."),
            "TSLA": ("1318605", "Tesla, Inc."),
            "PLTR": ("1321655", "Palantir Technologies Inc."),
            "AVGO": ("1730168", "Broadcom Inc."),
        }

    def _score_text(self, title: str):
        low = title.lower()
        score = 0
        notes = []
        if any(k in low for k in self.breaking):
            score += 4
            notes.append("Breaking-news language")
        pos = [w for w in self.strong_pos if w in low]
        soft = [w for w in self.soft_pos if w in low]
        neg = [w for w in self.strong_neg if w in low]
        rumor = [w for w in self.rumor if w in low]
        if pos:
            score += 18 + min(12, 3 * len(pos))
            notes.append("Strong positive catalyst: " + ", ".join(pos[:2]))
        if soft:
            score += 6 + min(6, 2 * len(soft))
            notes.append("Supportive headline context")
        if neg:
            score -= 18 + min(12, 3 * len(neg))
            notes.append("Strong negative catalyst: " + ", ".join(neg[:2]))
        if rumor:
            score -= 4
            notes.append("Rumor language present")
        return score, notes

    def _company_news(self, symbol: str, hours_back: int):
        if not self.finnhub_api_key:
            return []
        now = datetime.now(tz=UTC)
        start = now - timedelta(hours=hours_back)
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": symbol, "from": start.date().isoformat(), "to": now.date().isoformat(), "token": self.finnhub_api_key},
            timeout=30,
        )
        r.raise_for_status()
        out = []
        for row in r.json()[:10]:
            title = (row.get("headline") or "").strip()
            if title:
                out.append((row.get("source") or "Finnhub", title))
        return out

    def _sec_hits(self, symbol: str, hours_back: int):
        if not self.sec_user_agent or symbol not in self.sec_ciks:
            return []
        cik, company_name = self.sec_ciks[symbol]
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json",
            headers={"User-Agent": self.sec_user_agent, "Accept": "application/json"},
            timeout=30,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        recent = r.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        docs = recent.get("primaryDocument", [])
        cutoff = (datetime.now(tz=UTC) - timedelta(hours=max(hours_back, 72))).date()
        hits = []
        for form, date_str, doc in zip(forms, dates, docs):
            try:
                filing_date = datetime.fromisoformat(date_str).date()
            except Exception:
                continue
            if filing_date < cutoff:
                continue
            doc_low = (doc or "").lower()
            if form in {"SC 13D", "SC 13G", "13D", "13G"}:
                hits.append(f"{company_name} ownership / bought stake filing ({form})")
            elif form == "4":
                hits.append(f"{company_name} insider bought/sold filing (Form 4)")
            elif form == "8-K":
                if any(k in doc_low for k in ["acqui", "merger", "purchase", "agreement", "asset", "definitive"]):
                    hits.append(f"{company_name} possible acquisition / purchase 8-K")
                else:
                    hits.append(f"{company_name} material 8-K filing")
        return hits[:4]

    def assess_symbol(self, symbol: str, hours_back: int = 12) -> NewsAssessment:
        titles = []
        notes = []
        score = 0
        sec_hits = []
        try:
            for src, title in self._company_news(symbol, hours_back):
                titles.append(f"{src}: {title}")
                s, n = self._score_text(title)
                score += s
                if n:
                    notes.extend(n[:2])
        except Exception:
            pass

        try:
            sec_hits = self._sec_hits(symbol, hours_back)
            for hit in sec_hits:
                titles.append("SEC: " + hit)
                low = hit.lower()
                if any(k in low for k in ["acquisition", "purchase", "bought", "stake"]):
                    score += 22
                    notes.append("SEC buy/acquisition-type filing detected")
                elif "form 4" in low:
                    score += 12
                    notes.append("SEC insider filing detected")
                else:
                    score += 8
                    notes.append("SEC material filing detected")
        except Exception:
            pass

        if not notes:
            notes = ["No recent news catalysts found"] if not titles else ["News found but no strong catalyst keywords"]

        if score >= 28:
            priority = "BREAKING"
        elif score >= 18:
            priority = "HIGH"
        elif score <= -18:
            priority = "WARNING"
        elif abs(score) >= 8:
            priority = "MEDIUM"
        else:
            priority = "INFO"

        return NewsAssessment(symbol, score, notes[:5], titles[:5], priority, sec_hits)
