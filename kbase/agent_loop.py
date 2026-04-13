"""Agent Loop — async deep research with streaming progress. Copyright@PenguinMiaou

Architecture (Claude Research-inspired):
  User question → Decompose → Plan → Loop(generate queries → parallel search → extract → verify → assess) → Outline → Synthesize → Report
"""
import json
import time
import threading
import queue
from typing import Callable, Optional

from kbase.websearch import web_search


class AgentLoop:
    """Deep research agent that iteratively searches and synthesizes."""

    def __init__(self, llm_func: Callable, kb_search_func: Callable = None,
                 max_rounds: int = 10, urls_per_round: int = 20,
                 max_time_seconds: int = 600):
        self.llm = llm_func
        self.kb_search = kb_search_func
        self.max_rounds = max_rounds
        self.urls_per_round = urls_per_round
        self.max_time = max_time_seconds
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self, question: str, progress_queue: queue.Queue = None) -> dict:
        """Run the full research loop. Sends progress updates to queue."""
        start = time.time()
        all_findings = []
        all_sources = []
        searched_queries = set()
        total_urls = 0
        round_num = 0

        def emit(msg_type: str, data: dict):
            if progress_queue:
                progress_queue.put(json.dumps({"type": msg_type, **data}))

        emit("start", {"question": question, "max_rounds": self.max_rounds})

        # Phase 1: Decompose question into search plan
        emit("phase", {"name": "Planning", "name_zh": "规划搜索策略"})
        search_plan = self._plan_queries(question)
        emit("plan", {"queries": search_plan})

        # Phase 2: Iterative search loop
        pending_queries = list(search_plan)

        while round_num < self.max_rounds and not self._stop:
            elapsed = time.time() - start
            if elapsed > self.max_time:
                emit("timeout", {"elapsed": int(elapsed)})
                break

            if not pending_queries:
                # Generate follow-up queries based on findings
                if round_num > 0:
                    new_queries = self._generate_followup_queries(question, all_findings)
                    pending_queries = [q for q in new_queries if q not in searched_queries]
                    if not pending_queries:
                        emit("sufficient", {"reason": "No more queries to explore"})
                        break

            round_num += 1
            batch = pending_queries[:3]
            pending_queries = pending_queries[3:]

            emit("round", {
                "num": round_num, "queries": batch,
                "total_urls": total_urls, "elapsed": int(elapsed),
            })

            # Search each query
            round_findings = []
            for sq in batch:
                if self._stop:
                    break
                searched_queries.add(sq)

                # Web search
                emit("searching", {"query": sq, "source": "web"})
                try:
                    web_results = web_search(sq, max_results=self.urls_per_round)
                    for wr in web_results:
                        total_urls += 1
                        all_sources.append({
                            "name": wr.get("title", "")[:60],
                            "url": wr.get("url", ""),
                            "snippet": wr.get("snippet", ""),
                            "source": "web",
                        })
                        round_findings.append(f"[Web: {wr['title']}] {wr['snippet']}")
                except Exception as e:
                    emit("error", {"query": sq, "error": str(e)[:100]})

                # KB search
                if self.kb_search:
                    emit("searching", {"query": sq, "source": "kb"})
                    try:
                        kb_results = self.kb_search(sq)
                        for kr in kb_results:
                            meta = kr.get("metadata", {})
                            total_urls += 1
                            all_sources.append({
                                "name": meta.get("file_name", ""),
                                "path": meta.get("file_path", ""),
                                "source": "kb",
                            })
                            round_findings.append(f"[KB: {meta.get('file_name','')}] {kr.get('text','')[:300]}")
                    except Exception:
                        pass

            all_findings.extend(round_findings)
            emit("round_done", {
                "num": round_num, "new_findings": len(round_findings),
                "total_findings": len(all_findings), "total_urls": total_urls,
            })

            # Assess: do we have enough?
            if round_num >= 2 and len(all_findings) > 20:
                is_sufficient = self._assess_sufficiency(question, all_findings)
                if is_sufficient:
                    emit("sufficient", {"reason": "Enough information gathered"})
                    break

        # Phase 3: Build outline
        emit("phase", {"name": "Outlining", "name_zh": "构建报告框架"})

        # Phase 4: Synthesize report
        emit("phase", {"name": "Synthesizing", "name_zh": "撰写完整报告"})
        report = self._synthesize(question, all_findings, all_sources)

        elapsed = int(time.time() - start)
        emit("done", {
            "elapsed": elapsed, "rounds": round_num,
            "total_urls": total_urls, "total_findings": len(all_findings),
        })

        return {
            "report": report,
            "rounds": round_num,
            "total_urls": total_urls,
            "total_findings": len(all_findings),
            "elapsed_seconds": elapsed,
            "sources": all_sources[:20],
            "web_sources": [s for s in all_sources if s.get("source") == "web"][:10],
        }

    def _plan_queries(self, question: str) -> list:
        """Decompose question into sub-questions and search queries (Claude Research-style)."""
        try:
            prompt = (
                f"You are a senior research analyst planning a comprehensive investigation.\n\n"
                f"Question: {question}\n\n"
                f"Decompose this into 5-8 specific, diverse search queries that cover:\n"
                f"1. Core definitions and background\n"
                f"2. Current state / latest developments\n"
                f"3. Key players, stakeholders, or entities involved\n"
                f"4. Data, statistics, and metrics\n"
                f"5. Challenges, risks, and controversies\n"
                f"6. Expert opinions and analysis\n"
                f"7. Comparisons and alternatives\n\n"
                f"Return ONLY the queries, one per line. No numbering. Mix languages if the topic spans regions.\n"
                f"Each query should be specific enough to return targeted results."
            )
            result = self.llm(prompt)
            queries = [l.strip().strip("-").strip("•").strip("0123456789.").strip()
                       for l in result.strip().split("\n") if l.strip() and len(l.strip()) > 5]
            return queries[:8] if queries else [question]
        except Exception:
            return [question]

    def _generate_followup_queries(self, question: str, findings: list) -> list:
        """Generate targeted follow-up queries to fill knowledge gaps."""
        try:
            context = "\n".join(findings[-15:])[:3000]
            prompt = (
                f"You are assessing research completeness.\n\n"
                f"Original question: {question}\n\n"
                f"What we've found so far ({len(findings)} items):\n{context}\n\n"
                f"Identify 2-4 specific knowledge GAPS — what important aspects haven't been covered?\n"
                f"Generate targeted search queries to fill each gap.\n"
                f"Return ONLY queries, one per line. Be specific."
            )
            result = self.llm(prompt)
            return [l.strip().strip("-").strip("•").strip("0123456789.").strip()
                    for l in result.strip().split("\n") if l.strip() and len(l.strip()) > 5][:4]
        except Exception:
            return []

    def _assess_sufficiency(self, question: str, findings: list) -> bool:
        """Check coverage across key dimensions."""
        try:
            context = "\n".join(findings[-20:])[:3000]
            prompt = (
                f"You are a research quality assessor. Rate the completeness of our research.\n\n"
                f"Question: {question}\n\n"
                f"Findings ({len(findings)} total):\n{context}\n\n"
                f"Score each dimension 0-2 (0=missing, 1=partial, 2=covered):\n"
                f"- Background & context\n"
                f"- Key data & numbers\n"
                f"- Multiple perspectives\n"
                f"- Recent/current status\n"
                f"- Actionable insights\n\n"
                f"If total >= 7, reply 'SUFFICIENT'. Otherwise reply 'INSUFFICIENT: [what's missing]'."
            )
            result = self.llm(prompt).strip()
            return "SUFFICIENT" in result.upper()
        except Exception:
            return len(findings) > 30

    def _build_outline(self, question: str, findings: list) -> str:
        """Create a structured outline before synthesis (Claude Research-style)."""
        try:
            context = "\n".join(findings[:30])[:4000]
            prompt = (
                f"Create a detailed outline for a comprehensive research report.\n\n"
                f"Question: {question}\n\n"
                f"Available findings:\n{context}\n\n"
                f"Requirements:\n"
                f"- Use ## for main sections, ### for subsections\n"
                f"- Each section should note which findings to include\n"
                f"- Include an executive summary section at top\n"
                f"- Include key takeaways section at bottom\n"
                f"- Plan for data tables where appropriate\n"
                f"- Use the same language as the question\n\n"
                f"Return the outline only."
            )
            return self.llm(prompt)
        except Exception:
            return ""

    def _synthesize(self, question: str, findings: list, sources: list) -> str:
        """Create a comprehensive research report with outline-first approach."""
        try:
            # Step 1: Build outline
            outline = self._build_outline(question, findings)

            # Step 2: Synthesize with outline guidance
            context = "\n\n".join(findings[:50])[:10000]
            source_list = "\n".join(
                f"- {s.get('name','')}: {s.get('url','') or s.get('path','')}"
                for s in sources[:20]
            )
            prompt = (
                f"You are writing a comprehensive research report. Follow the outline below strictly.\n\n"
                f"OUTLINE:\n{outline}\n\n"
                f"RULES:\n"
                f"- Use the same language as the question\n"
                f"- Start with # title, then ## Executive Summary\n"
                f"- Use ## headings, ### subheadings, bullet points, and tables\n"
                f"- Cite EVERY claim using [source name] format\n"
                f"- Include specific data, numbers, dates, and quotes\n"
                f"- Cross-reference KB sources with web sources for verification\n"
                f"- End with ## Key Takeaways (actionable bullet points)\n"
                f"- If information conflicts between sources, note the discrepancy\n"
                f"- Minimum 800 words for substantive topics\n\n"
                f"QUESTION: {question}\n\n"
                f"RESEARCH FINDINGS ({len(findings)} items):\n{context}\n\n"
                f"SOURCES:\n{source_list}"
            )
            return self.llm(prompt)
        except Exception as e:
            return f"Synthesis error: {e}\n\nRaw findings ({len(findings)} items collected):\n" + "\n".join(findings[:10])
