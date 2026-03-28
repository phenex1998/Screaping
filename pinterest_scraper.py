#!/usr/bin/env python3
"""Scraper de Pinterest usando Playwright.

Exemplo:
    python pinterest_scraper.py \
      --url "https://www.pinterest.com/search/pins/?q=receitas" \
      --max-pins 100 \
      --output pins.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import Page, sync_playwright

PIN_PATH_RE = re.compile(r"/pin/(\d+)/")


@dataclass
class Pin:
    pin_id: str
    pin_url: str
    image_url: Optional[str]
    title: Optional[str]
    description: Optional[str]
    source_url: Optional[str]


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def extract_pin_id(pin_url: str) -> Optional[str]:
    match = PIN_PATH_RE.search(pin_url)
    return match.group(1) if match else None


def collect_pin_cards(page: Page) -> List[Dict[str, Optional[str]]]:
    """Extrai dados de cards já carregados no feed/página."""
    script = """
    () => {
      const anchors = Array.from(document.querySelectorAll('a[href*="/pin/"]'));
      const items = [];

      for (const a of anchors) {
        const href = a.getAttribute('href');
        if (!href || !href.includes('/pin/')) continue;

        const card = a.closest('[data-test-id], [data-grid-item], div');
        const img = (card || a).querySelector('img[src], img[srcset]');

        let imageUrl = null;
        if (img) {
          imageUrl = img.getAttribute('src');
          if (!imageUrl) {
            const srcset = img.getAttribute('srcset');
            if (srcset) {
              const options = srcset.split(',').map(s => s.trim().split(' ')[0]).filter(Boolean);
              imageUrl = options.length ? options[options.length - 1] : null;
            }
          }
        }

        const title = a.getAttribute('aria-label') || a.getAttribute('title') || null;
        let description = null;

        if (card) {
          const descEl = card.querySelector('[data-test-id="pinrep-description"], [data-test-id="pin-card-description"], p, h2, h3, span');
          if (descEl && descEl.textContent) {
            const txt = descEl.textContent.trim();
            if (txt.length) description = txt;
          }
        }

        items.push({
          href,
          image_url: imageUrl,
          title,
          description,
        });
      }

      return items;
    }
    """
    return page.evaluate(script)


def scroll_until(page: Page, max_pins: int, timeout_seconds: int) -> List[Pin]:
    deadline = time.time() + timeout_seconds
    pins_by_id: Dict[str, Pin] = {}
    stagnant_rounds = 0

    while len(pins_by_id) < max_pins and time.time() < deadline:
        raw_items = collect_pin_cards(page)
        before = len(pins_by_id)

        for item in raw_items:
            href = item.get("href")
            if not href:
                continue

            full_url = normalize_url(href)
            if full_url.startswith("/"):
                full_url = f"https://www.pinterest.com{full_url}"

            pin_id = extract_pin_id(full_url)
            if not pin_id:
                continue

            if pin_id not in pins_by_id:
                pins_by_id[pin_id] = Pin(
                    pin_id=pin_id,
                    pin_url=full_url,
                    image_url=normalize_url(item.get("image_url") or "") or None,
                    title=item.get("title"),
                    description=item.get("description"),
                    source_url=None,
                )

        after = len(pins_by_id)
        if after == before:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0

        if stagnant_rounds >= 6:
            break

        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(1000)

    return list(pins_by_id.values())[:max_pins]


def enrich_pin_details(page: Page, pin: Pin) -> Pin:
    """Abre uma página de pin e tenta extrair fonte e metadados."""
    page.goto(pin.pin_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1200)

    data = page.evaluate(
        """
        () => {
          const result = { source_url: null, title: null, description: null, image_url: null };

          const sourceA = document.querySelector('a[href^="http"]');
          if (sourceA) {
            const href = sourceA.getAttribute('href');
            if (href && !href.includes('pinterest.com')) result.source_url = href;
          }

          const ogImage = document.querySelector('meta[property="og:image"]');
          if (ogImage) result.image_url = ogImage.getAttribute('content');

          const ogTitle = document.querySelector('meta[property="og:title"]');
          if (ogTitle) result.title = ogTitle.getAttribute('content');

          const ogDesc = document.querySelector('meta[property="og:description"]');
          if (ogDesc) result.description = ogDesc.getAttribute('content');

          return result;
        }
        """
    )

    if data.get("source_url"):
        pin.source_url = normalize_url(data["source_url"])
    if data.get("title"):
        pin.title = data["title"]
    if data.get("description"):
        pin.description = data["description"]
    if data.get("image_url"):
        pin.image_url = normalize_url(data["image_url"])

    return pin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web scraping de Pinterest com rolagem automática.")
    parser.add_argument("--url", required=True, help="URL de busca, perfil ou board do Pinterest.")
    parser.add_argument("--max-pins", type=int, default=50, help="Quantidade máxima de pins para coletar.")
    parser.add_argument("--timeout", type=int, default=120, help="Tempo máximo total (segundos).")
    parser.add_argument("--output", default="pins.json", help="Arquivo de saída em JSON.")
    parser.add_argument(
        "--enrich-details",
        action="store_true",
        help="Abre cada pin para enriquecer os campos title/description/source_url (mais lento).",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Executa com navegador visível (debug). Padrão: headless.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.max_pins < 1:
        raise ValueError("--max-pins deve ser maior que 0")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1440, "height": 2400})
        page = context.new_page()

        page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)

        pins = scroll_until(page, max_pins=args.max_pins, timeout_seconds=args.timeout)

        if args.enrich_details and pins:
            for i, pin in enumerate(pins, start=1):
                try:
                    enrich_pin_details(page, pin)
                except Exception as exc:  # noqa: BLE001
                    print(f"[aviso] não foi possível enriquecer pin {pin.pin_id}: {exc}")
                if i % 10 == 0:
                    print(f"[info] enriquecidos {i}/{len(pins)}")

        context.close()
        browser.close()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(
            {
                "source_url": args.url,
                "total": len(pins),
                "pins": [asdict(pin) for pin in pins],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[ok] {len(pins)} pins salvos em: {output_path}")


if __name__ == "__main__":
    main()
