import asyncio
import json
from typing import Callable, Awaitable

from agents.variant_decoder import VariantDecoderAgent
from agents.protein_impact import ProteinImpactAgent
from agents.pharmacogenomics import PharmacogenomicsAgent
from agents.literature_clinical import LiteratureClinicalAgent


class Orchestrator:
    """Plan-and-Execute orchestrator — no external frameworks."""

    async def analyze(self, query: str, send: Callable[[str], Awaitable[None]]):
        async def emit(event: dict):
            await send(json.dumps(event))

        await emit({"type": "session_start", "data": {"query": query}})

        # ── Phase 1: Variant Decoding ────────────────────────────────────────
        decoder = VariantDecoderAgent()
        variant_data = {}

        async for event in decoder.run(query=query):
            await emit(event)
            # Capture variant_decoded payload for downstream agents
            if event.get("type") == "variant_decoded":
                variant_data = event.get("data", {})

        if not variant_data:
            # Build minimal variant_data from whatever we got
            variant_data = {"gene": "", "rs_id": "", "variant_type": "unknown",
                            "cdna_change": query, "chromosome": "", "position": None}

        # ── Phase 2: Parallel analysis ───────────────────────────────────────
        protein_agent = ProteinImpactAgent()
        pharma_agent = PharmacogenomicsAgent()
        lit_agent = LiteratureClinicalAgent()

        # Merge events from all three agents into a single async stream
        queue: asyncio.Queue = asyncio.Queue()
        active = 3

        async def run_agent(agent, **kwargs):
            nonlocal active
            try:
                async for event in agent.run(**kwargs):
                    await queue.put(event)
            except Exception as e:
                await queue.put(agent.error(str(e)))
            finally:
                active -= 1
                await queue.put(None)  # sentinel

        tasks = [
            asyncio.create_task(run_agent(protein_agent, variant_data=variant_data)),
            asyncio.create_task(run_agent(pharma_agent, variant_data=variant_data)),
            asyncio.create_task(run_agent(lit_agent, variant_data=variant_data)),
        ]

        sentinels_received = 0
        while sentinels_received < 3:
            item = await queue.get()
            if item is None:
                sentinels_received += 1
            else:
                await emit(item)

        await asyncio.gather(*tasks, return_exceptions=True)

        await emit({"type": "session_complete", "data": {
            "gene": variant_data.get("gene", ""),
            "variant": variant_data.get("cdna_change", query),
            "rs_id": variant_data.get("rs_id", ""),
        }})
